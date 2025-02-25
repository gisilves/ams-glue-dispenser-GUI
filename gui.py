import sys
import threading
import time
import re
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QPushButton,
    QFileDialog, QLabel, QComboBox, QHBoxLayout
)
from PyQt5.QtCore import pyqtSignal, QObject
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import serial
import serial.tools.list_ports


class Communicator(QObject):
    update_status = pyqtSignal(str)


class GRBLController(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("GRBL G-code Sender with Enhanced Plot")
        self.resize(800, 600)

        self.serial_port = None
        self.sending = False
        self.connected = False
        self.gcode_lines = []
        self.coordinates = [(0, 0)]
        self.glued_coordinates = []
        self.thread = None
        self.comm = Communicator()
        self.comm.update_status.connect(self.update_status)
        self.x_coords = []
        self.y_coords = []
        self.init_ui()
        self.scan_ports()

    def init_ui(self):
        layout = QVBoxLayout()

        # Set layout margins and spacing to zero to minimize wasted space
        layout.setContentsMargins(0, 0, 0, 0)  # Left, Top, Right, Bottom margins
        layout.setSpacing(5)  # Minimal spacing between widgets

        # Status label at the top
        self.status_label = QLabel("Status: Idle")
        layout.addWidget(self.status_label)

        # Port selection and connection controls
        port_layout = QHBoxLayout()
        port_layout.setContentsMargins(0, 0, 0, 0)  # Minimize margins in the port layout
        port_layout.setSpacing(5)

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

        # Adjust the figure layout to minimize padding
        self.figure.subplots_adjust(left=0.05, right=0.95, bottom=0.05, top=0.95)

        # Add the canvas to the layout with a stretch factor of 1
        # This ensures the plot takes up most of the available space
        layout.addWidget(self.canvas, stretch=1)

        # Load G-code file button
        self.load_button = QPushButton("Load G-code File")
        self.load_button.setEnabled(False)
        self.load_button.clicked.connect(self.load_file)
        layout.addWidget(self.load_button)

        # Start/Stop Sending button
        self.start_button = QPushButton("Start Sending")
        self.start_button.clicked.connect(self.toggle_sending)
        self.start_button.setEnabled(False)
        layout.addWidget(self.start_button)

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
        file_path, _ = QFileDialog.getOpenFileName(self, "Open G-code File", "", "G-code Files (*.gcode *.nc *.txt)")
        if file_path:
            self.gcode_lines = self.parse_gcode(file_path)
            self.update_status("G-code file loaded and parsed.")
            self.plot_toolpath()
            if self.connected:
                self.start_button.setEnabled(True)
                
    def parse_gcode(self, file_path):
        code_lines = []
        # Append the origin (0, 0) as the starting point
        self.x_coords.append(0.0)
        self.y_coords.append(0.0)

        current_x, current_y = 0.0, 0.0
        is_relative = False
        command_pattern = re.compile(r'G(\d+)(?:X([-.\d]+))?(?:Y([-.\d]+))?')

        with open(file_path, 'r') as file:
            for line in file:
                code_lines.append(line)
                line = line.strip().upper()
                if 'G90' in line:
                    is_relative = False
                elif 'G91' in line:
                    is_relative = True

                matches = command_pattern.finditer(line)
                for match in matches:
                    x = float(match.group(2)) if match.group(2) else 0.0
                    y = float(match.group(3)) if match.group(3) else 0.0
                    if is_relative:
                        current_x += x
                        current_y += y
                    else:
                        if match.group(2) is not None:
                            current_x = x
                        if match.group(3) is not None:
                            current_y = y
                    self.x_coords.append(current_x)
                    self.y_coords.append(current_y)

        self.coordinates = list(zip(self.x_coords, self.y_coords))
        return code_lines

    def plot_toolpath(self, pointcolor='lightgray'):
        # Ensure the background plot is created only once
        if not hasattr(self, 'ax'):
            self.ax = self.figure.add_subplot(111)

        if self.coordinates:
            x_vals, y_vals = zip(*self.coordinates)

            # Plot the toolpath in light gray as the background
            self.ax.plot(x_vals, y_vals, linestyle='-', color=pointcolor, label='Toolpath')  
            self.ax.scatter(x_vals, y_vals, color=pointcolor, s=50)  

            self.ax.set_xlim(-50, 1200)  # X-axis range
            self.ax.set_ylim(-50, 350)   # Y-axis range
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

    def toggle_sending(self):
        if self.sending:
            self.sending = False
            self.start_button.setText("Start Sending")
            self.update_status("Sending stopped.")
        else:
            self.sending = True
            self.start_button.setText("Stop Sending")
            self.thread = threading.Thread(target=self.send_gcode)
            self.thread.start()

    def send_gcode(self):
        if not self.serial_port:
            self.update_status("No serial connection.")
            return

        is_relative = False
        self.coordinates = [(0, 0)]
        self.update_status("Started sending G-code.")
        print("Sending G-code...")
        for line in self.gcode_lines:
            print(line)
            if not self.sending:
                break
            
            line = line.strip().upper()

            if 'G90' in line:
                is_relative = False
            elif 'G91' in line:
                is_relative = True
            
            # If it's a movement command, update the plot with the new position
            command_pattern = re.compile(r'G(\d+)(?:X([-.\d]+))?(?:Y([-.\d]+))?')
            if line.startswith('G0') or line.startswith('G1'):
                match = command_pattern.search(line)
                x = float(match.group(2)) if match.group(2) else 0.0
                y = float(match.group(3)) if match.group(3) else 0.0
                if is_relative:
                    x += self.coordinates[-1][0]
                    y += self.coordinates[-1][1]
                else:
                    if match.group(2) is not None:
                        x = x
                    if match.group(3) is not None:
                        y = y

                self.coordinates.append((x, y))

            if line.startswith('M4'):
                # Update the plot with the new coordinates
                self.plot_toolpath(pointcolor='red')

            self.serial_port.write((line + '\\n').encode())
            grbl_response = self.serial_port.readline().decode().strip()
            # Only proceed if the response is not empty
            if grbl_response:
                print(f"Sent: {line} | Response: {grbl_response}")
            else:
                print(f"Sent: {line} | No response")

            self.comm.update_status.emit(f"Sent: {line} | Response: {grbl_response}")

        self.comm.update_status.emit("Finished sending G-code.")
        self.start_button.setText("Start Sending")
        self.sending = False

    def update_status(self, message):
        self.status_label.setText(f"Status: {message}")

    def closeEvent(self, event):
        if self.serial_port and self.serial_port.is_open:
            self.serial_port.close()
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = GRBLController()
    # Open maximized
    window.showMaximized()
    sys.exit(app.exec_())