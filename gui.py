import sys
import threading
import time
import re
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QPushButton,
    QFileDialog, QLabel, QComboBox, QHBoxLayout, QMessageBox
)
from PyQt5.QtGui import QIcon
from PyQt5.QtCore import pyqtSignal, QObject
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import serial
import serial.tools.list_ports
import ctypes

class Communicator(QObject):
    update_status = pyqtSignal(str)


class GRBLController(QWidget):
    def __init__(self):
        super().__init__()
            
        self.setWindowTitle("AMS PG GLUE DISPENSER")
        self.resize(800, 600)

        self.serial_port = None
        self.sending = False
        self.paused = False
        self.connected = False
        self.coordinates = [(0, 0)]
        self.glued_coordinates = [(0,0)]
        self.thread = None
        self.comm = Communicator()
        self.comm.update_status.connect(self.update_status)
        self.init_ui()
        self.scan_ports()

    def init_ui(self):
        layout = QVBoxLayout()

        # Status label at the top
        self.status_label = QLabel("Status: Idle")
        self.status_label.setStyleSheet("""
            font-size: 18px; 
            font-weight: bold; 
            color: white; 
            background-color: #2e3a47;
            padding: 10px;
            border-radius: 5px;
        """)
        layout.addWidget(self.status_label)

        # Port selection and connection controls
        port_layout = QHBoxLayout()
        self.port_selector = QComboBox()
        port_layout.addWidget(self.port_selector)

        self.baud_selector = QComboBox()
        self.baud_selector.addItems(["9600", "115200", "250000"])
        self.baud_selector.setCurrentText("115200")
        port_layout.addWidget(self.baud_selector)

        self.connect_button = QPushButton("Connect")
        self.connect_button.clicked.connect(self.toggle_connection)
        port_layout.addWidget(self.connect_button)

        layout.addLayout(port_layout)

        # Matplotlib Figure and Canvas
        self.figure = Figure()
        self.canvas = FigureCanvas(self.figure)
        self.figure.subplots_adjust(left=0.05, right=0.95, bottom=0.05, top=0.95)
        layout.addWidget(self.canvas, stretch=1)

        # Add an empty plot to the canvas
        self.ax = self.figure.add_subplot(111)
        # Disable the axes
        self.ax.axis('off')

        # Add 'logo.png' to the plot
        self.ax.imshow(plt.imread('logo.png'))

        

        # Load G-code file button
        self.load_button = QPushButton("Load G-code File")
        self.load_button.setEnabled(False)
        self.load_button.clicked.connect(self.load_file)
        layout.addWidget(self.load_button)


        settings_layout = QHBoxLayout()

        # Add a selection for the first block to send with a label
        settings_layout.addWidget(QLabel("First Block:"))
        self.first_block_selector = QComboBox()
        settings_layout.addWidget(self.first_block_selector)
        self.first_block_selector.setEnabled(False)  # Initially disabled

        # Add a selection for the last block to send
        settings_layout.addWidget(QLabel("Last Block:"))
        self.last_block_selector = QComboBox()
        settings_layout.addWidget(self.last_block_selector)
        self.last_block_selector.setEnabled(False)

        layout.addLayout(settings_layout)

        # Start/Stop/Pause buttons
        button_layout = QHBoxLayout()
        
        self.start_button = QPushButton("Start Sending")
        self.start_button.clicked.connect(self.start_sending)
        self.start_button.setEnabled(False)  # Initially disabled
        button_layout.addWidget(self.start_button)

        self.pause_button = QPushButton("Pause")
        self.pause_button.clicked.connect(self.toggle_pause)
        self.pause_button.setEnabled(False)  # Initially disabled
        button_layout.addWidget(self.pause_button)

        self.stop_button = QPushButton("Stop")
        self.stop_button.clicked.connect(self.stop_sending)
        self.stop_button.setEnabled(False)  # Initially disabled
        button_layout.addWidget(self.stop_button)

        layout.addLayout(button_layout)

        # Set the layout for the main window
        self.setLayout(layout)

    def scan_ports(self):
        self.port_selector.clear()
        ports = serial.tools.list_ports.comports()
        for port in ports:
            self.port_selector.addItem(f"{port.device} - {port.description}", port.device)
        if self.port_selector.count() == 0:
            self.update_status("No serial ports found.")

    def toggle_connection(self):
        if self.connected:
            self.disconnect_serial()
        else:
            self.init_serial()

    def init_serial(self):
        selected_port = self.port_selector.currentData()
        baud_rate = int(self.baud_selector.currentText())
        if selected_port:
            try:
                self.serial_port = serial.Serial(selected_port, baud_rate, timeout=1)
                time.sleep(2)
                self.serial_port.write(b"\r\n\r\n")
                time.sleep(2)
                self.serial_port.flushInput()
                self.connected = True
                self.connect_button.setText("Disconnect")
                self.update_status(f"Connected to {selected_port} at {baud_rate} baud.")
                self.load_button.setEnabled(True)
            except serial.SerialException as e:
                self.update_status(f"Serial error: {e}")
        else:
            self.update_status("No port selected.")

    def disconnect_serial(self):
        if self.serial_port and self.serial_port.is_open:
            self.serial_port.close()
        self.connected = False
        self.connect_button.setText("Connect")
        self.start_button.setEnabled(False)
        self.update_status("Disconnected from serial port.")

    def load_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Open G-code File", "", "G-code Files (*.gcode)")
        if file_path:
            self.coordinates = [(0, 0)]  # Reset coordinates
            self.glued_coordinates = [(0, 0)]
            self.parse_gcode(file_path)
            self.update_status("G-code file loaded and parsed.")
            if hasattr(self, 'ax'): # Clear plot if a file was previously loaded
                self.ax.cla()
            self.plot_toolpath()  # Plot the original toolpath
            if self.connected:
                self.start_button.setEnabled(True)  # Enable Start button after file load
                self.first_block_selector.setEnabled(True)
                self.last_block_selector.setEnabled(True)

    def parse_gcode(self, file_path):
        self.movement_type = []
        self.toolpath = []  # List of {'x': ..., 'y': ..., 'glue_commands': [...]}
        self.program_initialization = []  # Stores the init block

        current_x, current_y = 0.0, 0.0
        is_relative = False
        in_init_block = False
        in_glue_block = False
        movement_type = '0'
        current_glue_commands = []

        command_pattern = re.compile(r'G(\d+)(?:X([-.\d]+))?(?:Y([-.\d]+))?')

        with open(file_path, 'r') as file:
            for line in file:
                line = line.strip()

                if '; Program initialization' in line:
                    in_init_block = True
                    self.program_initialization = [line]
                    continue
                elif '; End of program initialization' in line:
                    in_init_block = False
                    self.program_initialization.append(line)
                    continue

                if in_init_block:
                    self.program_initialization.append(line)
                    if 'G90' in line:
                        is_relative = False
                    elif 'G91' in line:
                        is_relative = True
                    if 'G00' or 'G01' in line:
                        x, y, movement_type = self.match_pattern(line, command_pattern)

                        if is_relative:
                            current_x += x
                            current_y += y
                        else:
                            current_x = x
                            current_y = y

                        self.coordinates.append((current_x, current_y))
                        self.movement_type.append(movement_type)
                        
                if "; ------- Glue deposition -------" in line:
                    in_glue_block = True
                    current_glue_commands = [line]
                    continue
                elif "; ------- End of glue deposition -------" in line:
                    in_glue_block = False
                    current_glue_commands.append(line)
                    if self.coordinates:
                        x, y = self.coordinates[-1]
                        self.toolpath.append({'x': x, 'y': y, 'glue_commands': current_glue_commands.copy(), 'movement_type' : self.movement_type[-1]})
                    current_glue_commands = []
                    continue

                if in_glue_block:
                    current_glue_commands.append(line)


                x, y, movement_type = self.match_pattern(line, command_pattern)

                if is_relative:
                    current_x += x
                    current_y += y
                else:
                    current_x = x
                    current_y = y

                self.coordinates.append((current_x, current_y))
                self.movement_type.append(movement_type)

            # Update the first and last block selectors
            self.first_block_selector.clear()
            self.first_block_selector.addItems([str(i) for i in range(len(self.toolpath))])
            self.first_block_selector.setCurrentIndex(0)

            self.last_block_selector.clear()
            self.last_block_selector.addItems([str(i) for i in range(len(self.toolpath))])
            self.last_block_selector.setCurrentIndex(len(self.toolpath) - 1)
                
    def match_pattern(self, line, pattern):
        x = 0.0
        y = 0.0
        movement_type = '0'
        
        matches = pattern.finditer(line.upper())
        for match in matches:
            x = float(match.group(2)) if match.group(2) else 0.0
            y = float(match.group(3)) if match.group(3) else 0.0

            if match.group(1) == '00' or match.group(1) == '01':
                movement_type = match.group(1)
    
        return x, y, movement_type
    
    def plot_toolpath(self, pointcolor='lightgray'):
        # Ensure the background plot is created only once
        if not hasattr(self, 'ax'):
            self.ax = self.figure.add_subplot(111)

        if self.coordinates:
            x_vals, y_vals = zip(*self.coordinates)
            self.ax.plot(x_vals, y_vals, linestyle='--', color=pointcolor, label='Toolpath')
            self.ax.scatter(x_vals, y_vals, color=pointcolor, s=50)

        self.ax.set_xlim(-50, max(x_vals) + 50)
        self.ax.set_ylim(-50, max(y_vals) + 50)
        
        self.ax.set_xlabel("X Axis")
        self.ax.set_ylabel("Y Axis")
        self.ax.set_title("G-code Toolpath Visualization")
        self.ax.grid(True)
        self.ax.set_aspect('equal', adjustable='box')

        self.canvas.draw()

    def plot_glued_toolpath(self):
        # No need to clear the axes, we just add to the existing one
        if self.glued_coordinates:
            x_vals, y_vals = zip(*self.glued_coordinates)

            # Plot the glued toolpath in red (foreground)
            self.ax.plot(x_vals, y_vals, linestyle='-', color='red', label='Glued Toolpath')  
            self.ax.scatter(x_vals, y_vals, color='red', s=50)

            self.ax.set_xlim(-50, 1200)  # X-axis range
            self.ax.set_ylim(-50, 350)   # Y-axis range
            self.ax.set_xlabel("X Axis")
            self.ax.set_ylabel("Y Axis")
            self.ax.set_title("G-code Toolpath Visualization (Glued)")
            self.ax.grid(True)
            self.ax.set_aspect('equal', adjustable='box')

        self.canvas.draw()

    def toggle_pause(self):
        if self.paused:
            self.paused = False
            self.pause_button.setStyleSheet("") 
            self.update_status("Resumed sending G-code.")
        else:
            self.paused = True
            self.pause_button.setStyleSheet("background-color : yellow") 
            self.update_status("Paused sending G-code.")

    def stop_sending(self):
        self.sending = False
        self.paused = False
        self.start_button.setEnabled(True)
        self.update_status("G-code sending stopped.")
        self.pause_button.setEnabled(False)
        self.stop_button.setEnabled(False)

    def start_sending(self):
        if not self.connected:
            self.update_status("Not connected to the device.")
            return

        self.sending = True
        self.paused = False
        self.start_button.setEnabled(False)
        self.pause_button.setEnabled(True)
        self.stop_button.setEnabled(True)

        self.thread = threading.Thread(target=self.send_gcode)
        self.thread.start()

    def send_gcode(self):
        try:
            # Send the program initialization block
            self.comm.update_status.emit("Starting G-code transmission")
            self.send_lines(self.program_initialization)
            self.send_lines(["G90"])  # Ensure absolute positioning (coordinates are converted during parsing to absolute)

            first_block = int(self.first_block_selector.currentText())
            last_block = int(self.last_block_selector.currentText())
            # Disable the first and last block selectors while sending
            self.first_block_selector.setEnabled(False)
            self.last_block_selector.setEnabled(False)

            # Send each command block in the toolpath
            for block in self.toolpath[first_block:last_block]:
                if not self.sending:
                    break
                while self.paused:
                    time.sleep(0.1)
                # Send movement command
                self.send_lines([f"G{block['movement_type']} X{block['x']} Y{block['y']}"])
                # Send glue deposition commands
                self.send_lines(block['glue_commands'])
                self.glued_coordinates.append((block['x'], block['y']))
                self.plot_glued_toolpath()

            self.comm.update_status.emit("Finished sending G-code.")
        except serial.SerialException as e:
            self.comm.update_status.emit(f"Serial error: {e}")
            self.sending = False
        except Exception as e:
            self.comm.update_status.emit(f"Error: {e}")
            self.sending = False
        finally:
            self.comm.update_status.emit("Transmission stopped")
            self.start_button.setEnabled(True)
            self.pause_button.setEnabled(False)
            self.stop_button.setEnabled(False)

    def send_lines(self, lines):
        for line in lines:
            if not self.sending:
                break
            while self.paused:
                time.sleep(0.1)

            try:
                self.serial_port.write((line + '\n').encode())
                self.comm.update_status.emit(f"Sent: {line}")

                while True:
                    response = self.serial_port.readline().decode().strip()
                    if response == 'ok':
                        break
                    time.sleep(0.1)

            except serial.SerialException as e:
                self.comm.update_status.emit(f"Serial error while sending: {e}")
                self.sending = False
                break
            except Exception as e:
                self.comm.update_status.emit(f"Error while sending: {e}")
                self.sending = False
                break

    def print_lines(self, lines):
        for line in lines:
            if not self.sending:
                break
            while self.paused:
                time.sleep(0.1)
            print((line))
            self.comm.update_status.emit(f"Sent: {line}")
            time.sleep(1)

    def update_status(self, message):
        self.status_label.setText(f"Status: {message}")
        
    def closeEvent(self, event):
        # Ask for confirmation before closing the application
        reply = QMessageBox.question(
            self, "Message", "Are you sure you want to quit?", QMessageBox.Yes, QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            if self.serial_port and self.serial_port.is_open:
                self.serial_port.close()
            event.accept()
        else:
            event.ignore()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = GRBLController()
    window.showMaximized()
    window.setWindowIcon(QIcon('icon.png'))
    sys.exit(app.exec_())
