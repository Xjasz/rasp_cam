class ServoUnavailableError(Exception):
    pass

class ServoKit(object):
    default_up_down = 135
    default_left_right = 110

    def __init__(self, num_ports):
        print("Initializing the servo...")
        try:
            from adafruit_servokit import ServoKit as AdafruitServoKit
        except Exception as ex:
            raise ServoUnavailableError("adafruit_servokit is not installed or cannot be imported") from ex
        try:
            self.kit = AdafruitServoKit(channels=16)
        except Exception as ex:
            raise ServoUnavailableError("Servo controller was not detected or could not be initialized") from ex
        self.num_ports = num_ports
        self.resetAll()
        print("Initializing complete.")

    def _validate_port(self, port):
        if port not in (0, 1):
            raise ValueError(f"Invalid servo port: {port}")
        if port >= self.num_ports:
            raise ValueError(f"Servo port {port} is outside configured port count {self.num_ports}")

    def _limits_for_port(self, port):
        self._validate_port(port)
        if port == 0:
            return 20, 180
        return 20, 170

    def setAngle(self, port, angle):
        min_angle, max_angle = self._limits_for_port(port)
        angle = max(min_angle, min(max_angle, angle))
        self.kit.servo[port].angle = angle

    def getAngle(self, port):
        self._validate_port(port)
        return self.kit.servo[port].angle

    def reset(self, port):
        self._validate_port(port)
        if port == 0:
            self.kit.servo[port].angle = self.default_up_down
        elif port == 1:
            self.kit.servo[port].angle = self.default_left_right

    def resetAll(self):
        for port in range(min(self.num_ports, 2)):
            self.reset(port)

def start():
    servoKit = ServoKit(2)

if __name__ == "__main__":
    start()