from ._mercury import Mercury

class Triton(Mercury):
    def __init__(self, visa_address, rm = None):
        super().__init__(visa_address, rm)
    
    def get_temp(self, channel: int) -> float:
        return self.query_number(f"READ:DEV:T{channel}:TEMP:SIG:TEMP")
    
    def get_MCRuO2_temp(self) -> float:
        return self.get_temp(8)
    
    def get_MCCernox_temp(self) -> float:
        return self.get_temp(5)
    
    def get_magnet_temp(self) -> float:
        return self.get_temp(13)
