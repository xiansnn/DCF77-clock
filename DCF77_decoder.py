import uasyncio, ustruct
from lib_pico.async_push_button import Button

import micropython
micropython.alloc_emergency_exception_buf(100)


from lib_pico.ST7735_TextUIv2 import *

# 
# from debug_utility.pulses import Probe
# probe_gpio = 16
# probe = Probe(probe_gpio)
# 

class DCF_Decoder():
    """
    """
    def __init__(self, key_in_gpio, local_time, display):
        self._DCF_clock_received = uasyncio.ThreadSafeFlag()
        self._DCF_frame_received = uasyncio.ThreadSafeFlag()
        Button("tone", key_in_gpio, pull=-1,
               interrupt_service_routine=self._DCF_clock_IRQ_handler,
               debounce_delay=80,
               active_HI=True, both_edge=True )
        self._time = local_time
        self._status_controller = _StatusController(display)
        self._current_string = ""
        self._frame = "" 
        self._DCF_signal_duration =0
        self._DCF_signal_is_high = True
        self._DCF_clock_received = uasyncio.ThreadSafeFlag()
   
    def _push(self, data):
        self._current_string += data
        self._status_controller.signal_received(self._current_string)
        if data == "#" :
            self._frame = self._current_string
            self._current_string = ""
  
    def _DCF_clock_IRQ_handler(self, button):
        irq_state = machine.disable_irq()
        self._DCF_signal_duration = button.last_event_duration
        self._DCF_signal_is_high = button.is_pressed           
        if self._DCF_signal_is_high :
            # we check the previous low level duration:
            # - about 800ms means previous hi-level is 200ms (i.e. logic "1")
            # - about 900ms means previous hi-level is 100ms (i.e. logic "0")
            # - more than 1000ms means we've had a 1-second signal that means "next minute"
            # including 800ms or 900ms for the last parity 59th bit 
            if self._DCF_signal_duration >= 750 and self._DCF_signal_duration < 850 :
                self._push("1") # we record a logic "1" signal
            elif self._DCF_signal_duration >= 850 and self._DCF_signal_duration < 950 :
                self._push("0") # we record a logic "0" signal
            elif self._DCF_signal_duration >= 1750 and self._DCF_signal_duration < 1950 :
                if self._DCF_signal_duration < 1850 :
                    self._push("1")
                else :
                    self._push("0")
                self._push("#") # we record a "next minute" signal (coded by "#")
                self._DCF_frame_received.set()
   
        self._DCF_clock_received.set()
        machine.enable_irq(irq_state)     
        
    def _BCD_decoder(self, string):
        BCD_weight = [1, 2, 4, 8, 10, 20, 40, 80]
        value = 0
        for k in range(len(string)):
            value += BCD_weight[k]*int(string[k])
        return value
    
    def _frame_parity_is_valid(self):
        s0 = (self._frame[0]  == "0") # check start of frame, always "0"
        s1 = (self._frame[20] == "1") # check start of time encoding, always "1"
        p1 = (self._frame[21:29].count("1")%2 == 0) # check parity
        p2 = (self._frame[29:36].count("1")%2 == 0) # check parity
        p3 = (self._frame[36:59].count("1")%2 == 0) # check parity
        return (s0 and s1 and p1 and p2 and p3)        

    def _all_bits_received(self):
        return len(self._frame)==60
        
    async def frame_decoder(self):
        """ coroutine that decodes DCF signal, triggered by the reception of End of Frame"""
        while True:
            await self._DCF_frame_received.wait()
            self._time.start_new_minute()
            if not self._all_bits_received():   
                self._status_controller.frame_incomplete(len(self._frame))
            else:
                if not self._frame_parity_is_valid():
                    self._status_controller.frame_parity_error()
                else: # we have now, a full frame without reception error
                    self._status_controller.frame_OK()
                    time_zone_num = self._BCD_decoder(self._frame[17:19])
                    minutes = self._BCD_decoder(self._frame[21:28])
                    hours = self._BCD_decoder(self._frame[29:35])
                    day = self._BCD_decoder(self._frame[36:42])
                    week_day_num = self._BCD_decoder(self._frame[42:45])
                    month_num = self._BCD_decoder(self._frame[45:50])
                    year = self._BCD_decoder(self._frame[50:58])
                    self._time.update_time(ustruct.pack("6HB",
                         year, month_num, day, week_day_num, hours, minutes, time_zone_num))

    async def DCF_signal_monitoring(self):
        while True:
            try:
                await uasyncio.wait_for_ms(self._DCF_clock_received.wait(), 4000)
                self._DCF_clock_received.clear()

            except uasyncio.TimeoutError:
                self._status_controller.signal_timeout() 


class _StatusController():
    """
    """    
    def __init__(self, display):
        self.display = display
        # init_frame_decoding
        self.time_status = _StatusController.START_DECODING
        self.time_event  = _StatusController.START_DECODING
        self.display.update_time_status(self.time_event, self.time_status)
        # init signal status management
        self.signal_status = _StatusController.SIGNAL_INIT
        self.signal_event  = _StatusController.SIGNAL_INIT
        self.display.update_signal_status( "x",self.signal_event, self.signal_status)
        
    # Signal status management
    #signal states
    SIGNAL_INIT = const("SIGNAL_INIT")
    SIGNAL_LOST = const("SIGNAL_LOST")
    SIGNAL_LATE = const("SIGNAL_LATE")
    SIGNAL_RECEPTION_OK = const("RECEPTION_OK")
    #signal events
    SIGNAL_RECEIVED = const("SIGNAL_RECEIVED")
    SIGNAL_TIMEOUT  = const("SIGNAL_TIMEOUT")
    def update_signal_status(self, current_string, event, new_status):
        self.signal_event =event
        self.signal_status = new_status
        self.display.update_signal_status(current_string, self.signal_event, self.signal_status)
        
    def signal_received(self, current_string):
        event = _StatusController.SIGNAL_RECEIVED
        if self.time_status == _StatusController.OUT_OF_SYNC:
            self.start_decoding()
        self.update_signal_status(current_string, event, _StatusController.SIGNAL_RECEPTION_OK)
    
    def signal_timeout(self):
        event = _StatusController.SIGNAL_TIMEOUT
        if (self.signal_status == _StatusController.SIGNAL_LATE) :
            self.update_signal_status(None, event, _StatusController.SIGNAL_LOST)
            self.out_of_sync()
        elif (self.signal_status == _StatusController.SIGNAL_LOST) :
            self.update_signal_status( None, event, _StatusController.SIGNAL_LOST)
        else:
            self.update_signal_status( None, event, _StatusController.SIGNAL_LATE)

    # Time/Calendar status management
    #time states
    TIME_INIT = const("TIME_INIT")
    OUT_OF_SYNC = const("OUT_OF_SYNC")
    SYNC_IN_PROGRESS = const("SYNC_IN_PROGRESS")
    SYNC_FAILED = const("SYNC_FAILED")
    #time events
    START_DECODING = const("START_DECODING")
    SYNC = const("SYNC")
    FRAME_ERROR = const("FRAME_PARITY_ERROR")
    MISSING_DATA = const("MISSING_DATA")
    END_OF_DECODING = const("END_OF_DECODING")
    
    def update_time_status(self, new_status, message=""):
        self.time_event = self.time_status
        self.time_status = new_status
        self.display.update_time_status(self.time_event, self.time_status, message)

        # entering new state
    def out_of_sync(self):
        self.update_time_status(_StatusController.OUT_OF_SYNC)
    def start_decoding(self):
        self.update_time_status(_StatusController.START_DECODING)
    def sync_failed(self, error, message):
        self.update_time_status(error, message)
        self.update_time_status(_StatusController.END_OF_DECODING)
    def sync_done(self):
        self.update_time_status(_StatusController.SYNC)
        self.update_time_status(_StatusController.END_OF_DECODING)       

        # processing event
    def new_minute_received(self):
        self.start_decoding()
    def frame_parity_error(self):
        self.sync_failed(_StatusController.FRAME_ERROR, "")
        self.start_decoding()        
    def frame_incomplete(self, frame_size):
        message = f"frame size: {str(frame_size)}"
        self.sync_failed(_StatusController.MISSING_DATA, message)
        self.start_decoding()
    def frame_OK(self):
        self.sync_done()
        self.start_decoding()
    
    



  
###############################################################################
    

if __name__ == "__main__":
    
    TONE_GPIO = const(7) # the GPIO where DCF signal is received by MCU
    
    class LocalTimeCalendar_stub():
        def __init__(self, display):
            print("\t\tinit LocalTimeCalendar_stub")
            self.year = 0
            self.month = "xxx"
            self._month_values = ["xxx","JAN","FEV","MAR","AVR","MAI","JUN","JUL","AOU","SEP","OCT","NOV","DEC"]
            self.day = 0
            self.week_day = "xxx"
            self._week_day_values = ["xxx","LUN","MAR","MER","JEU","VEN","SAM","DIM"]
            self.hours = 0
            self.minutes = 0
            self.time_zone = "xxx" #CET = +1, CEST = +2
            self._time_zone_values = ["GMT","CEST","CET"]

      
        def update_time(self, time_pack):
            (year, month, day, week_day, hours, minutes, time_zone) = ustruct.unpack("6HB",time_pack)
            self.year = year
            self.month = self._month_values[month]
            self.day = day
            self.week_day = self._week_day_values[week_day]
            self.hours = hours
            self.minutes = minutes
            self.time_zone = self._time_zone_values[time_zone]
            print(f"\t\t\t\t\t\t\tDCF calendar:\t{self.week_day} {self.day} {self.month} 20{self.year}")
            print(f"\t\t\t\t\t\t\tDCF time:\t\t{self.hours:0>2d}:{self.minutes:0>2d}\t\tzone:{self.time_zone}")

        def start_new_minute(self):
            print(f"\t\tstart_new_minute")


    class DCF_Display_stub():
        def __init__(self):
            print("\t\tinit DCF_Display_stub")
            
        def update_time_status(self, event, new_status, message=""):
            print(f"\t\t\t\t\t\t\t--{event:^20s}-->[{new_status:^20s}] : '{message}'")
   
        def update_signal_status(self, current_string, event, new_status):
            if current_string != None:
                data = current_string[-1]
                rank = len(current_string)-1
                print(f"--{event:^20s}-->[{new_status:^20s}] : Data[{rank:0>2d}] = {data}")
            else:
                print(f"--{event:^20s}-->[{new_status:^20s}] : No Data")
    
    
    

    ################### test ############################ 
    # init main tasks
    display = DCF_Display_stub()
    local_clock_calendar = LocalTimeCalendar_stub(display)
    DCF_decoder = DCF_Decoder(TONE_GPIO, local_clock_calendar, display)

    # setup coroutines
    DCF_frame_coroutine = DCF_decoder.frame_decoder()
    DCF_signal_monitor_coroutine = DCF_decoder.DCF_signal_monitoring()

    #start coroutines
    def excepHandler(loop, context):
        print(loop, context)
    scheduler = uasyncio.get_event_loop()
    scheduler.set_exception_handler(excepHandler)
    scheduler.create_task(DCF_signal_monitor_coroutine)
    scheduler.create_task(DCF_frame_coroutine)
    scheduler.run_forever()


