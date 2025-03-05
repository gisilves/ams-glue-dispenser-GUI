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
from PyQt5.QtCore import pyqtSignal, QObject
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import serial
import serial.tools.list_ports
import os.path

class Communicator(QObject):
    update_status = pyqtSignal(str)
    first_block_signal = pyqtSignal()

class GRBLController(QWidget):
    show_message_box_signal = pyqtSignal()

    def __init__(self):
        """
        Initialize the GRBLController widget.

        This constructor sets up the main window for the AMS PG GLUE DISPENSER application, 
        initializes various attributes related to the serial communication, toolpath handling, 
        and UI components. It also connects signals for status updates and first block detection, 
        and initializes the user interface and available serial ports.

        Attributes:
            serial_port: Serial port object used for communication.
            sending: Boolean indicating if G-code is currently being sent.
            paused: Boolean indicating if the sending of G-code is paused.
            connected: Boolean indicating if the device is connected.
            coordinates: List of tuples representing toolpath coordinates.
            glued_coordinates: List of tuples representing coordinates with glue applied.
            maximumTravel: Maximum travel distance for the X axis.
            thread: Thread object for handling G-code sending in a separate thread.
            comm: Communicator object for emitting and connecting signals.
            debug: Boolean indicating if the application is in debug mode.
        """

        super().__init__()

        self.setWindowTitle("AMS PG GLUE DISPENSER")
        self.resize(800, 600)

        self.serial_port = None
        self.sending = False
        self.paused = False
        self.connected = False
        self.coordinates = [(0, 0)]
        self.glued_coordinates = [(0, 0)]
        self.maximumTravel = 990
        self.thread = None
        self.comm = Communicator()
        self.comm.update_status.connect(self.update_status)
        self.comm.first_block_signal.connect(self.first_point_reached)
        self.show_message_box_signal.connect(self.show_message_box)
        
        self.init_ui()
        self.scan_ports()

        self.debug = False

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

        self.small_enabled_button_style = """
            QPushButton {
                font-size: 16px;           /* Font size */
                font-weight: bold;         /* Bold text */
                min-width: 30px;           /* Minimum width */
                min-height: 30px;         /* Minimum height */
            }
        """

        self.enabled_button_style = """
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

        self.disabled_button_style = """
            QPushButton {
                background-color: #bfbfbf;  /* Gray background */
                color: white;              /* White text */
                border: none;              /* No border */
                border-radius: 10px;       /* Rounded corners */
                padding: 10px;            /* Padding */
                font-size: 16px;           /* Font size */
                font-weight: bold;         /* Bold text */
                min-width: 60px;           /* Minimum width */
                min-height: 60px;         /* Minimum height */
            }
        """

        # Connection layout (always visible)
        port_layout = QHBoxLayout()
        self.port_selector = QComboBox()
        port_layout.addWidget(self.port_selector)

        # Refresh button
        refresh_button = QPushButton("Refresh")
        refresh_button.clicked.connect(self.scan_ports)
        refresh_button.setStyleSheet(self.small_enabled_button_style)
        port_layout.addWidget(refresh_button)


        self.baud_selector = QComboBox()
        self.baud_selector.addItems(["9600", "115200", "250000"])
        self.baud_selector.setCurrentText("115200")
        port_layout.addWidget(self.baud_selector)

        self.connect_button = QPushButton("Connect")
        self.connect_button.clicked.connect(self.toggle_connection)
        self.connect_button.setStyleSheet(self.small_enabled_button_style)
        port_layout.addWidget(self.connect_button)


        # Retrieve refresh button size
        refresh_button_size = refresh_button.sizeHint()
        refresh_button_height = refresh_button_size.height()
        self.port_selector.setFixedHeight(refresh_button_height)
        self.baud_selector.setFixedHeight(refresh_button_height)
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
        if self.debug:
            print("Debug mode enabled.")
            # Add "DEBUG MODE" text to the plot
            self.ax.text(0.5, 0.5, "DEBUG MODE", fontsize=24, ha='center', va='center', color='red')
            self.ax.text(0.5, 0.4, "No serial communication", fontsize=16, ha='center', va='center', color='red')
            self.ax.text(0.5, 0.3, "G-code commands will only be printed on terminal", fontsize=16, ha='center', va='center', color='red')
        else:
            # Check if logo.png is present
            if os.path.isfile('logo.png'):
                self.ax.imshow(plt.imread('logo.png'))  # Logo as background
            else:
                self.ax.text(0.5, 0.5, "NORMAL MODE", fontsize=24, ha='center', va='center', color='red')
                self.ax.text(0.5, 0.4, "logo.png not found", fontsize=16, ha='center', va='center', color='red')
        self.main_tab_layout.addWidget(self.canvas)

        self.load_button = QPushButton("Load G-code File")
        self.load_button.setEnabled(False)
        self.load_button.clicked.connect(self.load_file)
        self.load_button.setStyleSheet(self.small_enabled_button_style)
        self.main_tab_layout.addWidget(self.load_button)

        # File label (always visible)
        self.file_label = QLabel("No file loaded")
        self.file_label.setStyleSheet("""
            font-size: 18px;
            font-weight: bold;
            border: 2px solid #2e3a47;
            padding: 10px;
            border-radius: 5px;
        """)
        
        
        # Retrieve Load button size
        load_button_size = self.load_button.sizeHint()
        load_button_height = load_button_size.height()
        self.file_label.setFixedHeight(load_button_height + 15)
        self.main_tab_layout.addWidget(self.file_label)

        settings_layout = QHBoxLayout()
        settings_layout.addWidget(QLabel("First Point:"))
        self.first_block_selector = QComboBox()
        self.first_block_selector.setEnabled(False)
        self.first_block_selector.setFixedHeight(load_button_height)
        settings_layout.addWidget(self.first_block_selector)

        settings_layout.addWidget(QLabel("Last Point:"))
        self.last_block_selector = QComboBox()
        self.last_block_selector.setEnabled(False)
        self.last_block_selector.setFixedHeight(load_button_height)
        settings_layout.addWidget(self.last_block_selector)

        self.main_tab_layout.addLayout(settings_layout)

        button_layout = QHBoxLayout()
        self.start_button = QPushButton("Start Sending")
        self.start_button.setEnabled(False)
        self.start_button.clicked.connect(self.start_sending)
        self.start_button.setStyleSheet(self.small_enabled_button_style)
        button_layout.addWidget(self.start_button)

        self.pause_button = QPushButton("Pause")
        self.pause_button.setEnabled(False)
        self.pause_button.clicked.connect(self.toggle_pause)
        self.pause_button.setStyleSheet(self.small_enabled_button_style)
        button_layout.addWidget(self.pause_button)

        self.stop_button = QPushButton("Stop")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.stop_sending)
        self.stop_button.setStyleSheet(self.small_enabled_button_style)
        button_layout.addWidget(self.stop_button)

        self.main_tab_layout.addLayout(button_layout)

        self.main_tab.setLayout(self.main_tab_layout)

        self.tabs.addTab(self.main_tab, "Main Control")

        # Tab 2 - Manual movement
        self.manual_tab = QWidget()
        self.manual_tab_layout = QHBoxLayout()

        self.manual_tab.setLayout(self.manual_tab_layout)
        self.tabs.addTab(self.manual_tab, "Manual Control (Work In Progress)")

        # Left side: Jog controls
        jog_controls_widget = QWidget()
        jog_layout = QVBoxLayout()
        grid = QGridLayout()

        # Jog Buttons
        self.btnYplus = QPushButton("Y+")
        self.btnYplus.setStyleSheet(self.disabled_button_style)
        self.btnYplus.setEnabled(False)
        self.btnYplus.setToolTip("Move Y-axis in the positive direction")

        self.btnYminus = QPushButton("Y-")
        self.btnYminus.setStyleSheet(self.disabled_button_style)
        self.btnYminus.setEnabled(False)
        self.btnYminus.setToolTip("Move Y-axis in the negative direction")

        self.btnXplus = QPushButton("X+")
        self.btnXplus.setStyleSheet(self.disabled_button_style)
        self.btnXplus.setEnabled(False)
        self.btnXplus.setToolTip("Move X-axis in the positive direction")

        self.btnXminus = QPushButton("X-")
        self.btnXminus.setStyleSheet(self.disabled_button_style)
        self.btnXminus.setEnabled(False)
        self.btnXminus.setToolTip("Move X-axis in the negative direction")

        self.btnHome = QPushButton("Home")
        self.btnHome.setStyleSheet(self.disabled_button_style)
        self.btnHome.setEnabled(False)
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
        x_steps_layout.addWidget(QLabel("X Step (mm):"))
        self.x_steps_selector = QLineEdit()
        self.x_steps_selector.setText("1")
        self.x_steps_selector.setFixedWidth(100)
        x_steps_layout.addWidget(self.x_steps_selector)
        additional_layout.addLayout(x_steps_layout)

        # Add Y steps control with label
        y_steps_layout = QHBoxLayout()
        y_steps_layout.addWidget(QLabel("Y Step (mm):"))
        self.y_steps_selector = QLineEdit()
        self.y_steps_selector.setText("1")
        self.y_steps_selector.setFixedWidth(100)
        y_steps_layout.addWidget(self.y_steps_selector)
        additional_layout.addLayout(y_steps_layout)

        # Add feed rate control with label
        feed_rate_layout = QHBoxLayout()
        feed_rate_layout.addWidget(QLabel("Feed Rate (mm/min):"))
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

        # Add the manual tab layout to the main layout

        position_display_widget.setLayout(position_display_layout)
        additional_layout.addWidget(position_display_widget)

        additional_controls_widget.setLayout(additional_layout)

        # Add separator line
        separator3 = QFrame()
        separator3.setFrameShape(QFrame.HLine)
        separator3.setFrameShadow(QFrame.Sunken)
        additional_layout.addWidget(separator3)

        button_layout = QHBoxLayout()
        self.GoTo0 = QPushButton("Point 0")
        self.GoTo0.clicked.connect(self.move_to_point0)
        self.GoTo0.setStyleSheet(self.disabled_button_style)
        self.GoTo0.setEnabled(False)
        button_layout.addWidget(self.GoTo0)

        self.GoToEnd = QPushButton("Ladder End")
        self.GoToEnd.clicked.connect(self.move_to_ladder_end)
        self.GoToEnd.setStyleSheet(self.disabled_button_style)
        self.GoToEnd.setEnabled(False)
        button_layout.addWidget(self.GoToEnd)

        self.lowerSyringe = QPushButton("Lower Syringe")
        self.lowerSyringe.setStyleSheet(self.disabled_button_style)
        self.lowerSyringe.clicked.connect(self.lower_syringe)
        self.lowerSyringe.setEnabled(False)
        button_layout.addWidget(self.lowerSyringe)

        self.raiseSyringe = QPushButton("Raise Syringe")
        self.raiseSyringe.setStyleSheet(self.disabled_button_style)
        self.raiseSyringe.clicked.connect(self.raise_syringe)
        self.raiseSyringe.setEnabled(False)
        button_layout.addWidget(self.raiseSyringe)

        self.dispense = QPushButton("Dispense")
        self.dispense.setStyleSheet(self.disabled_button_style)
        self.dispense.clicked.connect(self.dispense_glue)
        self.dispense.setEnabled(False)
        button_layout.addWidget(self.dispense)

        additional_layout.addLayout(button_layout)
        
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

    def move_to_point0(self):
        self.sending = True
        self.update_status("Moving to Point 0")
        if self.coordinates[1:]:
            x_vals, y_vals = zip(*self.coordinates[1:])
            x0 = min(x_vals)
            y0 = min(y_vals)
        else:
            QMessageBox.warning(self, "WARNING", "No coordinates loaded", QMessageBox.Abort)

        command = f"G0 X{x0} Y{y0}"
        if GRBLController.debug:
            self.print_lines([command])
        else:
            self.send_lines([command])
        self.sending = False

    def move_to_ladder_end(self):
        self.sending = True
        self.update_status("Moving to Ladder End")
        if self.coordinates[1:]:
            # Get values excluding point 0,0
            x_vals, y_vals = zip(*self.coordinates[1:])
            xEnd = max(x_vals)
            yEnd = min(y_vals)
        else:
            QMessageBox.warning(self, "WARNING", "No coordinates loaded", QMessageBox.Abort)

        command = f"G0 X{xEnd} Y{yEnd}"
        if GRBLController.debug:
            self.print_lines([command])
        else:
            self.send_lines([command])
        self.sending = False

    def lower_syringe(self):
        self.sending = True
        self.update_status("Lowering Syringe")
        command = "M4"
        if GRBLController.debug:
            self.print_lines([command])
        else:
            self.send_lines([command])
        self.sending = False

    def raise_syringe(self):
        self.sending = True
        self.update_status("Raising Syringe")
        command = "M3"
        if GRBLController.debug:
            self.print_lines([command])
        else:
            self.send_lines([command])
        self.sending = False

    def dispense_glue(self):
        self.sending = True
        self.update_status("Dispensing Glue")
        command1 = "M8"
        command2 = "M9"
        if GRBLController.debug:
            self.print_lines([command1])
            time.sleep(1)
            self.print_lines([command2])
        else:
            self.send_lines([command1])
            self.sleep(1)
            self.send_lines([command2])

    def manual_move(self):

        if self.sender() == self.btnYplus or self.sender() == self.btnXplus:
            direction = +1
        else:
            direction = -1

        axis = "Y" if self.sender() in [self.btnYplus, self.btnYminus] else "X"
        steps = int(self.x_steps_selector.text()) if axis == "X" else int(self.y_steps_selector.text())
        
        current_x, current_y = self.get_current_position()  # Replace with actual position tracking

        # If movement results in value less than 0, clip it to a bit over 0
        if {current_x + {direction * steps} if axis == "X" else current_y + {direction * steps}} < 0:
            command = f"G00 {axis}{current_x + 0.001 if axis == "X" else current_y + 0.001}"
        else:
            command = f"G00 {axis}{direction * steps}"

        self.sending = True
        self.update_status(f"Moving {axis} by {direction * steps} mm")

        if GRBLController.debug:
            print("In debug mode, not sending command.")
            self.print_lines([command])
        else:
            print("Sending command to serial port")
            self.send_lines([command])

        self.update_position(direction * steps if axis == "X" else 0, direction * steps if axis == "Y" else 0)
        self.sending = False

    def move_home(self):
        self.update_status("Moving to home position")
        self.sending = True
        command = "$H"
        if GRBLController.debug:
            self.print_lines([command])
            self.update_position(0, 0)  # Reset position to home
        else:
            self.send_lines([command])
            self.update_position(0, 0)  # Reset position to home
        self.sending = False
        

        self.btnYplus.setEnabled(True)
        self.btnYplus.setStyleSheet(self.enabled_button_style)
        self.btnYminus.setEnabled(True)
        self.btnYminus.setStyleSheet(self.enabled_button_style)
        self.btnXplus.setEnabled(True)
        self.btnXplus.setStyleSheet(self.enabled_button_style)
        self.btnXminus.setEnabled(True)
        self.btnXminus.setStyleSheet(self.enabled_button_style)

        self.GoTo0.setEnabled(True)
        self.GoTo0.setStyleSheet(self.enabled_button_style)

        self.GoToLadderEnd.setEnabled(True)
        self.GoToLadderEnd.setStyleSheet(self.enabled_button_style)

    def update_feed_rate(self, value):
        self.update_status(f"Setting feed rate to {value} mm/min")
        command = f"F{value}"
        
        if GRBLController.debug:
            self.print_lines([command])
        else:
            self.send_lines([command])
            

    def update_position(self, x_change, y_change):
        # Example logic to update the current position display
        current_x, current_y = self.get_current_position()  # Replace with actual position tracking
        new_x = current_x + x_change
        new_y = current_y + y_change
        self.x_display.display(f"{new_x:06.2f}")  # Update X display
        self.y_display.display(f"{new_y:06.2f}")  # Update Y display

    def get_current_position(self):
        # Replace with actual logic to get the current position
        # Read value from display for now
        return float(self.x_display.value()), float(self.y_display.value())
    
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
            self.send_lines('$X') # Unlock the machine

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
               
                # Enable home control
                self.btnHome.setEnabled(True)
                self.btnHome.setStyleSheet(self.enabled_button_style)

                # Enable syringe control
                self.lowerSyringe.setEnabled(True)
                self.lowerSyringe.setStyleSheet(self.enabled_button_style)
                self.raiseSyringe.setEnabled(True)
                self.raiseSyringe.setStyleSheet(self.enabled_button_style)
                self.dispense.setEnabled(True)
                self.dispense.setStyleSheet(self.enabled_button_style)

            except serial.SerialException as e:
                self.update_status(f"Serial error: {e}")
        else:
            if GRBLController.debug:
                self.load_button.setEnabled(True)
            self.update_status("No port selected.")

    def disconnect_serial(self):
        if self.serial_port and self.serial_port.is_open:
            self.serial_port.close()
        self.connected = False
        self.connect_button.setText("Connect")
        self.load_button.setEnabled(False)
        self.start_button.setEnabled(False)
        self.pause_button.setEnabled(False)
        self.stop_button.setEnabled(False)
        self.first_block_selector.setEnabled(False)
        self.last_block_selector.setEnabled(False)
        self.file_label.setText("File: None")
        self.btnHome.setEnabled(False)
        self.btnYminus.setEnabled(False)
        self.btnYplus.setEnabled(False)
        self.btnXminus.setEnabled(False)
        self.btnXplus.setEnabled(False)

        # Disable syringe control
        self.lowerSyringe.setEnabled(False)
        self.raiseSyringe.setEnabled(False)
        self.dispense.setEnabled(False)
        self.GoTo0.setEnabled(False)
        self.GoToEnd.setEnabled(False)
        
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
                self.file_label.setStyleSheet("""
                    font-size: 18px;
                    font-weight: bold;
                    padding: 10px;
                    border: 2px solid #2e3a47;
                    border-radius: 5px;
                """)
                self.file_label.setText(f"File: {file_path}")

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
                    
                    if '$130' in line:
                        self.maximumTravel = line[5:8]
                        
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

                if not in_init_block:
                    
                    x, y, movement_type = self.match_pattern(line, command_pattern)
                    
                    if 'G90' in line:
                        is_relative = False
                    elif 'G91' in line:
                        is_relative = True
                        
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

        # Find all unique x and y values
        unique_x = sorted(set(x_vals))
        unique_y = sorted(set(y_vals))

        col_num, row_num = 0, -1
        # Add a line for each unique x and y value
        for x in unique_x:
            self.ax.plot([x, x], [max(y_vals), max(y_vals) + 50], color='lightgray', linewidth=0.5)
            # Add text with column number
            self.ax.annotate(f"{col_num}", (x, max(y_vals) + 50), xytext=(0, 10), textcoords='offset points', ha='center', va='bottom', arrowprops=dict(arrowstyle='->', color='lightgray'))
            col_num += 1
        
        # Add a line for each unique y value
        for y in unique_y:
            self.ax.plot([max(x_vals), max(x_vals) + 50], [y, y], color='lightgray', linewidth=0.5)
            # Add text with row number
            self.ax.annotate(f"{row_num}", (max(x_vals) + 50, y), xytext=(-10, 0), textcoords='offset points', ha='right', va='center', arrowprops=dict(arrowstyle='->', color='lightgray'))
            row_num += 1

        self.ax.grid(True)
        self.ax.set_aspect('equal', adjustable='box')
        

        # Check if the last line is over the maximum allowed travel
        if max(x_vals) >= float(self.maximumTravel):
            QMessageBox.warning(self, "WARNING", "The last line is over the maximum allowed travel", QMessageBox.Ok)

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
            self.ax.grid(True)
            self.ax.set_aspect('equal', adjustable='box')

        self.canvas.draw()

    def toggle_pause(self):
        COLOR_PAUSED = "#FFEE8C"  # Light yellow

        if self.paused:
            self.paused = False
            status_message = "Resumed sending G-code."
            self.pause_button.setStyleSheet(self.small_enabled_button_style) 
        else:
            self.paused = True
            status_message = "Paused sending G-code."
            # Get the current style sheet
            current_style = self.pause_button.styleSheet().split("\n")
            # Reassemble the style sheet
            new_style = "\n".join(current_style[:-2] + [f"background-color: {COLOR_PAUSED};}}"])

            self.pause_button.setStyleSheet(new_style)

        # Update status
        self.update_status(status_message)

    def stop_sending(self):
        self.sending = False
        self.paused = False
        self.start_button.setEnabled(True)
        self.update_status("G-code sending stopped.")
        self.paused = False
        self.pause_button.setStyleSheet(self.small_enabled_button_style)
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

        # Clean up glued coordinates
        self.glued_coordinates = [(0, 0)]
        # Clean up glued toolpath
        if hasattr(self, 'ax'):
            self.ax.cla()
            self.plot_toolpath()

        self.thread = threading.Thread(target=self.send_gcode)
        self.thread.start()

    def send_gcode(self):
        try:
            # Send the program initialization block
            self.comm.update_status.emit("Starting G-code transmission")

            if GRBLController.debug:
                self.print_lines(self.program_initialization)
                self.print_lines(["G90"])  # Ensure absolute positioning (coordinates are converted during parsing to absolute)
            else:
                self.send_lines(self.program_initialization)
                self.send_lines(["G90"])

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
                if GRBLController.debug:
                    self.print_lines([f"G{block['movement_type']} X{block['x']} Y{block['y']}"])
                    if block == self.toolpath[first_block]:
                        print("First block reached, emitting signal")  # Debug print
                        self.comm.update_status.emit("First point reached")
                        self.comm.first_block_signal.emit()  # Emit the signal
                        time.sleep(5)
                else:
                    self.send_lines([f"G{block['movement_type']} X{block['x']} Y{block['y']}"])
                    if block == self.toolpath[first_block]:
                        self.comm.update_status.emit("First point reached")
                        self.first_block_signal.emit()  # Emit the signal
  

                # Send glue deposition commands
                if GRBLController.debug:
                    self.print_lines(block['glue_commands'])
                else:
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
            time.sleep(0.25)

    def update_status(self, message):
        self.status_label.setText(f"Status: {message}")

    def first_point_reached(self):
        self.toggle_pause()  # Pause the transmission
        self.show_message_box_signal.emit()  # Emit the signal to show the message box
    
    def show_message_box(self):
        print("Showing message box")  # Debug print
        reply = QMessageBox.question(
            self, "Message", "First point reached. Continue?", QMessageBox.Yes, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.toggle_pause()  # Resume the transmission
        else:
            self.stop_sending()  # Stop the transmission

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

    # If launched with -d or --debug flag, enable debug mode
    if len(sys.argv) > 1 and sys.argv[1] in ['-d', '--debug']:
        GRBLController.debug = True
    else:
        GRBLController.debug = False

    app = QApplication(sys.argv)
    window = GRBLController()
    window.showMaximized()
    window.setWindowIcon(QIcon('icon.ico'))
    sys.exit(app.exec_())
