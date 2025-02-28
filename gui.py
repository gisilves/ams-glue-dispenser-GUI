import sys
import threading
import time
import re
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QPushButton, QFileDialog, QLabel, 
    QComboBox, QHBoxLayout, QMessageBox, QTabWidget, QGridLayout, QFrame,
    QLCDNumber, QLineEdit
)
from PyQt5.QtGui import QIcon
from PyQt5.QtCore import pyqtSignal, QObject, Qt
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import serial
import serial.tools.list_ports

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
        self.glued_coordinates = [(0, 0)]
        self.thread = None
        self.comm = Communicator()
        self.comm.update_status.connect(self.update_status)

        self.init_ui()
        self.scan_ports()

    def init_ui(self):
        main_layout = QVBoxLayout()

        # Status label (always visible)
        self.status_label = QLabel("Status: Idle")
        self.status_label.setStyleSheet("""
            font-size: 18px; 
            font-weight: bold; 
            color: white; 
            background-color: #2e3a47;
            padding: 10px;
            border-radius: 5px;
        """)
        main_layout.addWidget(self.status_label)

        # Connection layout (always visible)
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

        main_layout.addLayout(port_layout)

        # Tab widget
        self.tabs = QTabWidget()

        # Tab 1 - Main GUI
        self.main_tab = QWidget()
        self.main_tab_layout = QVBoxLayout()

        self.figure = Figure()
        self.canvas = FigureCanvas(self.figure)
        self.figure.subplots_adjust(left=0.05, right=0.95, bottom=0.05, top=0.95)
        self.ax = self.figure.add_subplot(111)
        self.ax.axis('off')
        self.ax.imshow(plt.imread('logo.png'))  # Logo as background
        self.main_tab_layout.addWidget(self.canvas)

        self.load_button = QPushButton("Load G-code File")
        self.load_button.setEnabled(False)
        self.load_button.clicked.connect(self.load_file)
        self.main_tab_layout.addWidget(self.load_button)

        settings_layout = QHBoxLayout()
        settings_layout.addWidget(QLabel("First Block:"))
        self.first_block_selector = QComboBox()
        self.first_block_selector.setEnabled(False)
        settings_layout.addWidget(self.first_block_selector)

        settings_layout.addWidget(QLabel("Last Block:"))
        self.last_block_selector = QComboBox()
        self.last_block_selector.setEnabled(False)
        settings_layout.addWidget(self.last_block_selector)

        self.main_tab_layout.addLayout(settings_layout)

        button_layout = QHBoxLayout()
        self.start_button = QPushButton("Start Sending")
        self.start_button.setEnabled(False)
        self.start_button.clicked.connect(self.start_sending)
        button_layout.addWidget(self.start_button)

        self.pause_button = QPushButton("Pause")
        self.pause_button.setEnabled(False)
        self.pause_button.clicked.connect(self.toggle_pause)
        button_layout.addWidget(self.pause_button)

        self.stop_button = QPushButton("Stop")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.stop_sending)
        button_layout.addWidget(self.stop_button)

        self.main_tab_layout.addLayout(button_layout)

        self.main_tab.setLayout(self.main_tab_layout)

        self.tabs.addTab(self.main_tab, "Main Control")

        # Tab 2 - Manual movement
        self.manual_tab = QWidget()
        self.manual_tab_layout = QHBoxLayout()

        self.manual_tab.setLayout(self.manual_tab_layout)
        self.tabs.addTab(self.manual_tab, "Manual Control")

        # Left side: Jog controls
        jog_controls_widget = QWidget()
        jog_layout = QVBoxLayout()
        grid = QGridLayout()

        # Define a stylesheet for the buttons
        button_style = """
            QPushButton {
                background-color: #4CAF50;  /* Green background */
                color: white;              /* White text */
                border: none;              /* No border */
                border-radius: 10px;       /* Rounded corners */
                padding: 10px;            /* Padding */
                font-size: 16px;           /* Font size */
                font-weight: bold;         /* Bold text */
                min-width: 60px;           /* Minimum width */
                min-height: 60px;         /* Minimum height */
            }
            QPushButton:hover {
                background-color: #45a049; /* Darker green on hover */
            }
            QPushButton:pressed {
                background-color: #3d8b40; /* Even darker green when pressed */
            }
        """

        # Jog Buttons
        self.btnYplus = QPushButton("Y+")
        self.btnYplus.setStyleSheet(button_style)
        self.btnYplus.setToolTip("Move Y-axis in the positive direction")

        self.btnYminus = QPushButton("Y-")
        self.btnYminus.setStyleSheet(button_style)
        self.btnYminus.setToolTip("Move Y-axis in the negative direction")

        self.btnXplus = QPushButton("X+")
        self.btnXplus.setStyleSheet(button_style)
        self.btnXplus.setToolTip("Move X-axis in the positive direction")

        self.btnXminus = QPushButton("X-")
        self.btnXminus.setStyleSheet(button_style)
        self.btnXminus.setToolTip("Move X-axis in the negative direction")

        self.btnHome = QPushButton("Home")
        self.btnHome.setStyleSheet(button_style)
        self.btnHome.setToolTip("Move to the home position")

        # Add buttons to the grid
        grid.addWidget(self.btnYplus, 0, 1)
        grid.addWidget(self.btnYminus, 2, 1)
        grid.addWidget(self.btnXplus, 1, 2)
        grid.addWidget(self.btnXminus, 1, 0)
        grid.addWidget(self.btnHome, 1, 1)

        jog_layout.addLayout(grid)
        jog_controls_widget.setLayout(jog_layout)

        # Add jog controls to the left side of the manual tab
        self.manual_tab_layout.addWidget(jog_controls_widget)

        # Add a vertical separator line
        separator = QFrame()
        separator.setFrameShape(QFrame.VLine)
        separator.setFrameShadow(QFrame.Sunken)
        self.manual_tab_layout.addWidget(separator)

        # Right side: Additional controls
        additional_controls_widget = QWidget()
        additional_layout = QVBoxLayout()

        # Add spacing and margins to layouts
        jog_layout.setSpacing(10)
        jog_layout.setContentsMargins(10, 10, 10, 10)  # Left, Top, Right, Bottom

        additional_layout.setSpacing(10)
        additional_layout.setContentsMargins(10, 10, 10, 10)

        # Add X steps control with label
        x_steps_layout = QHBoxLayout()
        x_steps_layout.addWidget(QLabel("X Steps:"))
        self.x_steps_selector = QLineEdit()
        self.x_steps_selector.setText("1")
        self.x_steps_selector.setFixedWidth(100)
        x_steps_layout.addWidget(self.x_steps_selector)
        additional_layout.addLayout(x_steps_layout)

        # Add Y steps control with label
        y_steps_layout = QHBoxLayout()
        y_steps_layout.addWidget(QLabel("Y Steps:"))
        self.y_steps_selector = QLineEdit()
        self.y_steps_selector.setText("1")
        self.y_steps_selector.setFixedWidth(100)
        y_steps_layout.addWidget(self.y_steps_selector)
        additional_layout.addLayout(y_steps_layout)

        # Add feed rate control with label
        feed_rate_layout = QHBoxLayout()
        feed_rate_layout.addWidget(QLabel("Feed Rate:"))
        self.feed_rate_selector = QLineEdit()
        self.feed_rate_selector.setText("500")
        self.feed_rate_selector.setFixedWidth(100)
        feed_rate_layout.addWidget(self.feed_rate_selector)
        additional_layout.addLayout(feed_rate_layout)

        # Add horizontal separator line
        separator2 = QFrame()
        separator2.setFrameShape(QFrame.HLine)
        separator2.setFrameShadow(QFrame.Sunken)
        additional_layout.addWidget(separator2)

        # Add current position display (7-segment style using QLCDNumber)
        position_display_widget = QWidget()
        position_display_layout = QHBoxLayout()

        # X position display
        x_position_layout = QHBoxLayout()
        x_position_label = QLabel("Current X Position:")
        x_position_layout.addWidget(x_position_label)
        self.x_display = QLCDNumber()
        self.x_display.setDigitCount(6)  # Display 6 digits (e.g., 000.00)
        self.x_display.display("000.00")
        self.x_display.setSegmentStyle(QLCDNumber.Flat)  # Flat segment style
        self.x_display.setFixedHeight(50)
        x_position_layout.addWidget(self.x_display)
        position_display_layout.addLayout(x_position_layout)


        # Add spacer between X and Y displays
        spacer = QWidget()
        spacer.setFixedWidth(250)
        position_display_layout.addWidget(spacer)

        # Y position display
        y_position_layout = QHBoxLayout()
        y_position_label = QLabel("Current Y Position:")
        y_position_layout.addWidget(y_position_label)
        self.y_display = QLCDNumber()
        self.y_display.setDigitCount(6)  # Display 6 digits (e.g., 000.00)
        self.y_display.display("000.00")
        self.y_display.setSegmentStyle(QLCDNumber.Flat)  # Flat segment style
        self.y_display.setFixedHeight(50)
        y_position_layout.addWidget(self.y_display)
        position_display_layout.addLayout(y_position_layout)

        position_display_widget.setLayout(position_display_layout)
        additional_layout.addWidget(position_display_widget)

        additional_controls_widget.setLayout(additional_layout)

        # Add additional controls to the right side of the manual tab
        self.manual_tab_layout.addWidget(additional_controls_widget)

        # Add the tabs to the main layout
        main_layout.addWidget(self.tabs)
        self.setLayout(main_layout)

        # Connect controls to functions
        self.btnYplus.clicked.connect(self.manual_move)
        self.btnYminus.clicked.connect(self.manual_move)
        self.btnXplus.clicked.connect(self.manual_move)
        self.btnXminus.clicked.connect(self.manual_move)

        self.btnHome.clicked.connect(self.move_home)

        self.feed_rate_selector.textChanged.connect(self.update_feed_rate)

    # Example functions
    def manual_move(self):

        if self.sender() == self.btnYplus or self.sender() == self.btnXplus:
            direction = +1
        else:
            direction = -1

        axis = "Y" if self.sender() in [self.btnYplus, self.btnYminus] else "X"
        steps = float(self.y_steps_selector.currentText()) if axis == "Y" else float(self.x_steps_selector.currentText())

        command = f"G00 {axis}{direction * steps}"
        print(f"Moving {axis} by {direction * steps} steps")  # Replace with actual movement code

    def move_home(self):
        print("Moving to home position")  # Replace with actual movement code
        command = "$H"
        self.print_lines([command])
        # self.send_lines([command])
        self.update_position(0, 0)  # Reset position to home

    def update_feed_rate(self, value):
        print(f"Feed rate updated to: {value}")  # Replace with actual logic
        command = f"F{value}"
        self.print_lines([command])
        # self.send_lines([command])

    def update_position(self, x_change, y_change):
        # Example logic to update the current position display
        current_x, current_y = self.get_current_position()  # Replace with actual position tracking
        new_x = current_x + x_change
        new_y = current_y + y_change
        self.x_display.display(f"{new_x:06.2f}")  # Update X display
        self.y_display.display(f"{new_y:06.2f}")  # Update Y display

    def get_current_position(self):
        # Replace with actual logic to get the current position
        return 0.0, 0.0  # Placeholder

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
        port = self.port_selector.currentData()
        baud = int(self.baud_selector.currentText())
        if port:
            try:
                self.serial_port = serial.Serial(port, baud, timeout=1)
                time.sleep(2)
                self.serial_port.write(b"\r\n\r\n")
                time.sleep(2)
                self.serial_port.flushInput()
                self.connected = True
                self.connect_button.setText("Disconnect")
                self.update_status(f"Connected to {port} at {baud} baud.")
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
        x, y, movement_type = 0.0, 0.0, '0'
        
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
        #try:
        # Send the program initialization block
        self.comm.update_status.emit("Starting G-code transmission")
        self.print_lines(self.program_initialization)
        self.print_lines(["G90"])  # Ensure absolute positioning (coordinates are converted during parsing to absolute)

        first_block = int(self.first_block_selector.currentText())
        last_block = int(self.last_block_selector.currentText())
        # Disable the first and last block selectors while sending
        self.first_block_selector.setEnabled(False)
        self.last_block_selector.setEnabled(False)

        # Send each command block in the toolpath
        for block in self.toolpath[first_block:last_block + 1]:
            if not self.sending:
                break
            while self.paused:
                time.sleep(0.1)
            # Send movement command
            self.print_lines([f"G{block['movement_type']} X{block['x']} Y{block['y']}"])
            # Send glue deposition commands
            self.print_lines(block['glue_commands'])
            self.glued_coordinates.append((block['x'], block['y']))
            self.plot_glued_toolpath()

        self.comm.update_status.emit("Finished sending G-code.")
        # except serial.SerialException as e:
        #     self.comm.update_status.emit(f"Serial error: {e}")
        #     self.sending = False
        # except Exception as e:
        #     self.comm.update_status.emit(f"Error: {e}")
        #     self.sending = False
        # finally:
        #     self.comm.update_status.emit("Transmission stopped")
        #     self.start_button.setEnabled(True)
        #     self.pause_button.setEnabled(False)
        #     self.stop_button.setEnabled(False)

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
