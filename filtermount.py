import time

from thorlabs_elliptec import ELLx

# Status code for ELLStatus.UNKNOWN, per Thorlabs' Elliptec communications
# protocol. Compared as a raw int here instead of importing the ELLStatus
# enum, since its exact import path varies between thorlabs_elliptec
# versions (e.g. thorlabs_elliptec.ELLStatus vs thorlabs_elliptec.ellx.ELLStatus).
_ELL_STATUS_UNKNOWN = 14


class ELL6Bmanager:
    def __init__(self, port=None):

        """
        Initialize the ELL6Bmanager and connect to a Thorlabs ELL6B.

        Parameters
        ----------
        port : str, optional
            COM port used to communicate with the ELL6B, for example "COM3".
            If None, the ELLx class automatically searches for a connected device.

        Attributes
        ----------
        position_1_raw : int
            Raw encoder position corresponding to ELL6B position 1 (home position, where you ND filter is installed). Default: 0.

        position_2_raw : int
            Raw encoder position corresponding to ELL6B position 2. Default: 31.

        stage : ELLx
            Underlying Thorlabs Elliptec ELLx device object.

        port_name : str
            Actual COM port used by the ELL6B.

        current_position_raw : int
            Current raw encoder position read from the ELL6B.

        current_position : int
            Current logical position of the ELL6B. Either 1 or 2.

        Raises
        ------
        ValueError
            If the current raw position is neither 0 nor 31.

        Examples
        --------
        ell6 = ELL6Bmanager("COM3")

        Or automatically detect the device:

        ell6 = ELL6Bmanager()
        """
            
        # Calibrated ELL6B positions
        self.position_1_raw = int(0)
        self.position_2_raw = int(31)

        # Connect to ELL6B
        # If port is None, ELLx automatically finds a device.
        
        if port is None:
            self.stage = ELLx()
        else:
            self.stage = ELLx(serial_port=port)

        # Actual COM port
        self.port_name = self.stage.port_name

        # The ELLx driver starts polling the device's status ("gs") and
        # position ("gp") in a background thread as soon as it connects,
        # but that first poll is scheduled asynchronously and is *not*
        # finished by the time ELLx() returns. Until it finishes,
        # get_position_raw() just returns the placeholder value the
        # driver initializes it to (0), which we would misread as
        # "position 1" even if the mount is actually at position 2.
        #
        # The status and position are queried back-to-back in the same
        # poll cycle, so waiting for status to leave UNKNOWN is a
        # reliable signal that the position has also just been refreshed
        # from the real hardware.
        self._wait_for_first_status()

        # Read actual position from hardware
        self.current_position_raw = self.stage.get_position_raw()
        self.current_position = self._raw_to_position(
            self.current_position_raw
        )

    def _wait_for_first_status(self, timeout=3.0):
        """
        Block until the ELLx background thread has completed its first
        status/position poll, so that get_position_raw() reflects the
        real hardware instead of the driver's initial placeholder value.
        """
        start = time.monotonic()
        while int(self.stage.status) == _ELL_STATUS_UNKNOWN:
            if time.monotonic() - start > timeout:
                raise TimeoutError(
                    "Timed out waiting for the ELL6B to report its "
                    "status after connecting."
                )
            time.sleep(0.02)

    def _raw_to_position(self, raw_position):
        """Convert raw encoder position to logical position 1 or 2."""

        if raw_position == self.position_1_raw:
            return 1

        if raw_position == self.position_2_raw:
            return 2

        raise ValueError(
            f"Unknown ELL6B position: raw={raw_position}. "
            f"Expected 0 or 31."
        )

    def _update_position(self):
        """Read and update the current hardware position."""

        self.current_position_raw = int(self.stage.get_position_raw())
        self.current_position = self._raw_to_position(
            self.current_position_raw
        )

    def get_position(self):
        """Return the current logical position: 1 or 2."""

        self._update_position()
        return self.current_position

    def get_position_raw(self):
        """Return the current raw encoder position."""

        self._update_position()
        return self.current_position_raw


    def set_position(self, position):
        """Move ELL6B to position 1 or 2."""

        self._update_position()

        if position not in (1, 2):
            raise ValueError("Position must be 1 or 2.")

        target_raw = (
            self.position_1_raw
            if position == 1
            else self.position_2_raw
        )

        # Already there
        if self.current_position_raw == target_raw:
            return

        if position == 1:
            # Position 1 is home
            self.stage.home(blocking=True)

        elif position == 2:
            # Move to raw encoder position 31
            self.stage.move_absolute_raw(
                self.position_2_raw,
                blocking=True
            )

        # Verify actual position
        self._update_position()

    def close(self):
        """Close the ELL6B connection."""
        self.stage.close()