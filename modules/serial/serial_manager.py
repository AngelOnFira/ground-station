# The unfortunate manager of serial ports
# Handles connections, specifying what serial port a radio should use and spawning the serial processes
#
# Authors:
# Thomas Selwyn (Devil)
import glob
import threading
import sys
import time
from multiprocessing import Process, Queue, Value
from multiprocessing.shared_memory import ShareableList
from serial import Serial, SerialException
from modules.serial.serial_rn2483_radio import SerialRN2483Radio
from modules.serial.serial_rn2483_emulator import SerialRN2483Emulator


class SerialManager(Process):
    def __init__(self, serial_connected: Value, serial_connected_port: ShareableList, serial_ports: ShareableList,
                 serial_ws_commands: Queue, rn2483_radio_input: Queue, rn2483_radio_payloads: Queue):
        super().__init__()

        self.serial_ports = serial_ports
        self.serial_connected = serial_connected
        self.serial_connected_port = serial_connected_port

        self.serial_ws_commands = serial_ws_commands
        self.rn2483_radio_input = rn2483_radio_input
        self.rn2483_radio_payloads = rn2483_radio_payloads

        self.rn2483_radio = None

        # Immediately find serial ports
        self.serial_ports = self.update_serial_ports()

        self.run()

    def run(self):
        while True:
            while not self.serial_ws_commands.empty():
                ws_cmd = self.serial_ws_commands.get()
                self.parse_ws_command(ws_cmd)

    def parse_ws_command(self, ws_cmd):
        try:
            match ws_cmd[1]:
                case "rn2483_radio":
                    self.parse_rn2483_radio_ws(ws_cmd)
                case "update":
                    self.update_serial_ports()
                case _:
                    print("Serial: Invalid device type.")
        except IndexError:
            print("Serial: Error parsing ws command")

    def parse_rn2483_radio_ws(self, ws_cmd):
        try:
            if ws_cmd[2] == "connect":
                if not self.serial_connected.value:
                    if ws_cmd[3] != "test":
                        self.rn2483_radio = Process(target=SerialRN2483Radio, args=(self.serial_connected,
                                                                                    self.serial_connected_port,
                                                                                    self.serial_ports,
                                                                                    self.rn2483_radio_input,
                                                                                    self.rn2483_radio_payloads,
                                                                                    ws_cmd[3]),
                                                    daemon=True)
                    else:
                        self.rn2483_radio = Process(target=SerialRN2483Emulator,
                                                    args=(self.serial_connected, self.serial_connected_port,
                                                          self.serial_ports, self.rn2483_radio_payloads),
                                                    daemon=True)
                    self.serial_connected_port[0] = ws_cmd[3]
                    self.rn2483_radio.start()
                    time.sleep(.1)
                else:
                    print(f"Serial: Already connected.")

            if ws_cmd[2] == "disconnect":
                if self.rn2483_radio is not None:
                    if self.serial_connected_port[0] == "test":
                        print("Serial: RN2483 Payload Emulator terminating")
                    else:
                        print(f"Serial: RN2483 Radio on port {'N/A' if self.serial_connected_port[0] == '' else self.serial_connected_port[0]} terminating")

                    self.serial_connected.value = False
                    self.serial_connected_port[0] = ""
                    self.rn2483_radio.terminate()
                    self.rn2483_radio = None
                else:
                    print("Serial: RN2483 Radio already disconnected.")
        except IndexError:
            print("Serial: Not enough arguments.")

    def update_serial_ports(self) -> list[str]:
        """ Finds and updates serial ports on device

            :raises EnvironmentError:
                On unsupported or unknown platforms
            :returns:
                A list of the serial ports available on the system
        """
        com_ports = [""]

        if sys.platform.startswith('win'):
            com_ports = ['COM%s' % (i + 1) for i in range(256)]
        elif sys.platform.startswith('linux') or sys.platform.startswith('cygwin'):
            # '/dev/tty[A-Za-z]*'
            com_ports = glob.glob('/dev/ttyUSB*')
        elif sys.platform.startswith('darwin'):
            com_ports = glob.glob('/dev/tty.*')

        tested_com_ports = []

        # Checks ports if they are potential COM ports
        for test_port in com_ports:
            try:
                if test_port != self.serial_connected_port[0]:
                    ser = Serial(test_port)
                    ser.close()
                    tested_com_ports.append(test_port)
            except (OSError, SerialException):
                pass

        tested_com_ports = tested_com_ports + ["test"]

        for i in range(len(self.serial_ports)):
            self.serial_ports[i] = "" if i > len(tested_com_ports) - 1 else str(tested_com_ports[i])

        return tested_com_ports
