import uasyncio

# DEBUG probe definitions
from debug_utility.pulses import *
# D0 = Probe(27) # LocalTimeCalendar._timer_IRQ
# D1 = Probe(16) # DCF_Decoder._DCF_clock_IRQ_handler
# D2 = Probe(17) # DCF_Decoder.frame_decoder
# D3 = Probe(18) # DCF_Display_stub.update_time_status
# D4 = Probe(19) # DCF_Display_stub.update_signal_status
# D5 = Probe(20) # DCF_Display_stub.update_date_and_time
# D6 = Probe(21) # _StatusController.time_status == SYNC
# D7 = Probe(26) # DCF_Display_stub.update_seconds

from DCF77.DCF77_decoder import DCF_Decoder
from DCF77.local_time_calendar_IRQ import LocalTimeCalendar


class DCF_clock_manager():
    def __init__(self):
        print("init DCF_Display_stub")
        TONE_GPIO = const(7) # the GPIO where DCF signal is received by MCU
        self.local_clock_calendar = LocalTimeCalendar(self)
        self.DCF_decoder = DCF_Decoder(TONE_GPIO, self.local_clock_calendar, self)
        #---------------
        self.year = 2000
        self.month = "xxx" # in (JAN ...DEC)
        self.mday = 1 # in (1 ... 31)
        self.hour = 0 # in (0 ... 23)
        self.minute = 0 # in (0 ... 59)
        self.second = 0 # in (0 ... 59)
        self.weekday = "xxx" # in (LUN ... DIM)
        self.yearday = 1 # in (1 ... 366)
        self.time_zone = 0
        self.time_event = "x"
        self.time_state = "x"
        self.signal_event = "x"
        self.signal_state = "x"
        self.current_frame = "x"
        self.current_message = "x"
        
    def get_DCF_time(self):
        return [self.year, self.month, self.mday,  self.weekday, self.hour, self.minute, self.second, self.time_zone]
    
    def get_DCF_time_status(self):
        return [self.time_event, self.time_state, self.current_message]
    
    def get_DCF_signal_status(self):
        if self.current_frame!=None:
            last_frame_bit_value = self.current_frame[-1]
            last_frame_bit_rank = len(self.current_frame)-1
        else:
            last_frame_bit_value = "x"
            last_frame_bit_rank = 0
        return [last_frame_bit_rank, last_frame_bit_value, self.signal_event, self.signal_state]
  
    def update_time_status(self, event, new_status, message=""):
        self.time_event = event
        self.time_state = new_status
        self.current_message = message
        TIME_STATUS_TAB   = const("\t\t\t\t\t\t\t")
        D3.on()
        print(f"{TIME_STATUS_TAB}{self.get_DCF_time_status()}")
        D3.off()

    def update_signal_status(self, current_string, event, new_status):
        self.current_frame = current_string
        self.signal_event = event
        self.signal_state = new_status
        SIGNAL_STATUS_TAB = const("")
        D4.on()
        print(f"{SIGNAL_STATUS_TAB}{self.get_DCF_signal_status()}")
        D4.off()
            
    def update_date_and_time(self, DCF_clock_update):
        LOCAL_TIME_TAB    = const("\t\t\t\t\t\t\t")
        D5.on()
        self.weekday, self.mday, self.month, self.year, self.hour, self.minute, self.second, self.time_zone = DCF_clock_update
        print(f"{LOCAL_TIME_TAB}{self.get_DCF_time()}")
        D5.off()
        
    def update_seconds(self, seconds):
        D7.on()
        pass
        D7.off()


################### test ############################

if __name__ == "__main__":           
    # init main tasks
    dcf = DCF_clock_manager()
            #---------------
    # setup coroutines
    DCF_frame_coroutine = dcf.DCF_decoder.frame_decoder()
    DCF_signal_monitor_coroutine = dcf.DCF_decoder.DCF_signal_monitoring()
    local_time_coroutine = dcf.local_clock_calendar.next_second()
    
    #start coroutines
    scheduler = uasyncio.get_event_loop()
# 
    scheduler.create_task(DCF_signal_monitor_coroutine)
    scheduler.create_task(DCF_frame_coroutine)
    scheduler.create_task(local_time_coroutine)
# 
    scheduler.run_forever()



