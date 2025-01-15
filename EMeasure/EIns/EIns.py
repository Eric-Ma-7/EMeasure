import threading
import pyvisa

class EIns:
    def __init__(self, resource_name):
        self.resource_name = resource_name
        self.rm = pyvisa.ResourceManager()
        self.device = None
        self.IDN = None
        self._lock = threading.Lock()
    

    def connect(self):
        with self._lock:
            try:
                self.device = self.rm.open_resource(self.resource_name)
                print(f"Connected to {self.resource_name}")
            except Exception as e:
                print(f"Failed to connect to {self.resource_name}: {e}")
    

    def disconnect(self):
        with self._lock:
            if self.device:
                self.device.close()
                self.device = None
                print(f"Disconnected from {self.resource_name}")
    

    def write(self, command):
        with self._lock:
            if self.device:
                try:
                    self.device.write(command)
                    # print(f"Command '{command}' sent to {self.resource_name}")
                except Exception as e:
                    print(f"Failed to send command '{command}' to {self.resource_name}: {e}")
    

    def read(self):
        with self._lock:
            if self.device:
                try:
                    response = self.device.read()
                    # print(f"Response from {self.resource_name}: {response.strip()}")
                    return response
                except Exception as e:
                    print(f"Failed to read response from {self.read}: {e}")
                    return None
    

    def query(self, command):
        with self._lock:
            if self.device:
                try:
                    response = self.device.query(command)
                    # print(f"Query '{command}' sent to {self.resource_name}, response: {response.strip()}")
                    return response
                except Exception as e:
                    print(f"Failed to query '{command}' from {self.resource_name}: {e}")
                    return None


    def get_IDN(self):
        self.IDN = self.query('*IDN?')
        return self.IDN
    

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.disconnect()