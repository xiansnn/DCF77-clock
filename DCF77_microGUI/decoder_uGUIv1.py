import uasyncio, ustruct, machine
from lib_pico.async_push_button import Button as DCF_signal_in

import micropython
micropython.alloc_emergency_exception_buf(100)

from debug_utility.pulses import *
# D0 = Probe(26) # -- time_trigger  
# D1 = Probe(16) # DCF_Decoder._DCF_clock_IRQ_handler
# D2 = Probe(17) # DCF_Decoder.frame_decoder
# D3 = Probe(18) # DCF_Display_stub.display_time_status
# D4 = Probe(19) # _StatusController.signal_received
# D5 = Probe(20) # _StatusController.signal_timeout
# D6 = Probe(21) # -- time_status == SYNC
# D7 = Probe(27) # DCF_Display_stub.display_signal_status


#SIGNAL
## signal states
SIGNAL_INIT = const("SIGNAL_INIT")
SIGNAL_RECEPTION_OK = const("RECEPTION_OK")
SIGNAL_LATE = const("SIGNAL_LATE")
SIGNAL_LOST = const("SIGNAL_LOST")
## signal events
SIGNAL_RECEIVED = const("SIGNAL_RECEIVED")
SIGNAL_TIMEOUT  = const("SIGNAL_TIMEOUT")

#TIME
## time states
TIME_INIT = const("TIME_INIT")
OUT_OF_SYNC = const("OUT_OF_SYNC")
SYNC_IN_PROGRESS = const("SYNC_IN_PROGRESS")
SYNC_FAILED = const("SYNC_FAILED")
SYNC = const("SYNC")
## time events
EoF_RECEIVED = const("EOF")
FRAME_ERROR = const("FRAME_ERROR")
FRAME_OK = const("FRAME_OK")
MISSING_DATA = const("WRONG_NUMBER_OF_DATA")



class DCF_Decoder():
    def __init__(self, key_in_gpio, local_time):
        self._DCF_clock_received = uasyncio.ThreadSafeFlag()
        self._DCF_frame_received = uasyncio.ThreadSafeFlag()
        DCF_signal_in("tone", key_in_gpio, pull=-1,
               interrupt_service_routine=self._DCF_clock_IRQ_handler,
               debounce_delay=80,
               active_HI=True, both_edge=True )
        self._local_time = local_time
        self._status_controller = self._StatusController()
        self._frame = ""
        self._current_string = ""
        self._DCF_signal_duration =0
        self._DCF_signal_is_high = True
    
    def get_time_status(self):
        return [self._status_controller.time_event, self._status_controller.time_state, self._status_controller.error_message]

    def get_signal_status(self):
        return [self._status_controller.last_received_frame_bit_rank, self._status_controller.last_received_frame_bit,
                self._status_controller.signal_event, self._status_controller.signal_state]

    def _push(self, data):
        self._current_string += data
        self._status_controller.signal_received(data, len(self._current_string))
        if data == "#" :
            self._frame = self._current_string
            self._current_string = ""
  
    def _DCF_clock_IRQ_handler(self, button):
        D1.on()
        self._DCF_clock_received.set()
        irq_state = machine.disable_irq()
        self._DCF_signal_duration = button.last_event_duration
        self._DCF_signal_is_high = button.is_pressed           
        if self._DCF_signal_is_high :
            # we check the previous low level duration:
            # - about 800ms means previous hi-level is 200ms long (i.e. logic "1")
            # - about 900ms means previous hi-level is 100ms long (i.e. logic "0")
            # - more than 1000ms means we've had a 1-second silent signal that means "next minute"
            #   including 800ms or 900ms for the 59th bit 
            if self._DCF_signal_duration >= 750 and self._DCF_signal_duration < 850 :
                self._push("1") # we record a logic "1" signal
            elif self._DCF_signal_duration >= 850 and self._DCF_signal_duration < 950 :
                self._push("0") # we record a logic "0" signal
            elif self._DCF_signal_duration >= 1750 and self._DCF_signal_duration < 1950 :
                if self._DCF_signal_duration < 1850 :
                    self._push("1") # we record a logic last "1" signal
                else :
                    self._push("0") # we record a logic last "0" signal
                self._push("#") # we record a "next minute" signal (coded by "#")
                self._DCF_frame_received.set()
        machine.enable_irq(irq_state)
        D1.off()
         
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
            D2.off()
            await self._DCF_frame_received.wait()
            D2.on()
            if not self._all_bits_received():   
                self._status_controller.frame_incomplete(len(self._frame))
            else:
                if not self._frame_parity_is_valid():
                    self._status_controller.frame_parity_error()
                else: # finally we have received a full frame without reception error
                    self._status_controller.frame_OK()
                    time_zone_num = self._BCD_decoder(self._frame[17:19])
                    minutes = self._BCD_decoder(self._frame[21:28])
                    hours = self._BCD_decoder(self._frame[29:35])
                    day = self._BCD_decoder(self._frame[36:42])
                    week_day_num = self._BCD_decoder(self._frame[42:45])
                    month_num = self._BCD_decoder(self._frame[45:50])
                    year = self._BCD_decoder(self._frame[50:58])
                    self._local_time.sync_time(ustruct.pack("6HB",
                         year, month_num, day, week_day_num, hours, minutes, time_zone_num))

    async def DCF_signal_monitoring(self):
        while True:
            try:
                await uasyncio.wait_for_ms(self._DCF_clock_received.wait(), 2000)
                self._DCF_clock_received.clear()

            except uasyncio.TimeoutError:
                self._status_controller.signal_timeout() 

    class _StatusController():
        def __init__(self):
            # init time and signal status management
            self.set_time_status(TIME_INIT, SYNC_IN_PROGRESS, "")
            self.set_signal_status(1,"x",SIGNAL_INIT,SIGNAL_INIT) 
            
        # Signal status management
        def set_signal_status(self, frame_size, data, new_event, new_status):
            self.last_received_frame_bit_rank = frame_size -1
            self.last_received_frame_bit = data            
            self.signal_event = new_event
            self.signal_state = new_status
            
        def signal_received(self, data, frame_size):
            D4.on()
            if self.time_state == OUT_OF_SYNC:
                self.restart_sync()
            event = SIGNAL_RECEIVED
            self.set_signal_status(frame_size, data, event, SIGNAL_RECEPTION_OK)
            D4.off()
        
        def signal_timeout(self):
            D5.on()
            if (self.signal_state == SIGNAL_LATE) :
                self.set_signal_status( 0, None, SIGNAL_TIMEOUT, SIGNAL_LOST)
                self.out_of_sync()
            elif (self.signal_state == SIGNAL_LOST) :
                self.set_signal_status( 0, None, SIGNAL_TIMEOUT, SIGNAL_LOST)
            else:
                self.set_signal_status( 0, None, SIGNAL_TIMEOUT, SIGNAL_LATE)
            D5.off()

        # Time/Calendar status management
        def set_time_status(self, new_event, new_status, message=""):
            self.time_event = new_event
            self.time_state = new_status
            self.error_message = message
            if new_status == SYNC :
                D6.on()
            else:
                D6.off()

            # entering new state
        def out_of_sync(self):
            self.set_time_status(SIGNAL_LOST ,OUT_OF_SYNC)
        def sync_failed(self, error, message):
            self.set_time_status(error, SYNC_FAILED, message)
        def sync_done(self):
            self.set_time_status(FRAME_OK, SYNC)
        def restart_sync(self):
            self.set_time_status(SIGNAL_RECEIVED, SYNC_IN_PROGRESS)

            # processing event
        def frame_parity_error(self):
            self.sync_failed(FRAME_ERROR, "parity error")
        def frame_incomplete(self, frame_size):
            message = f"frame size: {str(frame_size)}"
            self.sync_failed(MISSING_DATA, message)
        def frame_OK(self):
            self.sync_done()
    
    



  
###############################################################################
if __name__ == "__main__":
    print("test")
    from machine import Timer
                
######################### stub    
    class DCF_Display_stub():
        def __init__(self):
            print("init DCF_Display_stub")
            self._month_values = ("JAN","FEV","MAR","AVR","MAI","JUN","JUL","AOU","SEP","OCT","NOV","DEC")
            self._week_day_values = ("LUN","MAR","MER","JEU","VEN","SAM","DIM")
                
        def display_date_and_time(self, clock_update):
            LOCAL_TIME_TAB = const("\t\t\t\t\t\t\t\t\t\t\t\t")
            # raw_time_and_date : t[0]:year, t[1]:month, t[2]:mday, t[3]:hour, t[4]:minute, t[5]:second, t[6]:weekday, t[7]:time_zone, t[8]:time_is_valid
            year, month_num, mday, hour, minute, second, week_day_num, time_zone, time_is_valid = clock_update
#             print(f"{LOCAL_TIME_TAB}LocalTime: {clock_update}")
            print(f"{LOCAL_TIME_TAB}LocalTime: {self._week_day_values[week_day_num-1]:3s} {mday:02d} {self._month_values[month_num-1]:3s} {year:4d} {hour:02d}:{minute:002d}:{second:02d} UTC{time_zone:+01d} time is valid:{time_is_valid}")
            
        def display_time_status(self, time_status):
            TIME_STATUS_TAB   = const("\t\t\t\t\t\t")
            D3.on()
            print(f"{TIME_STATUS_TAB}{time_status}")
            D3.off()
   
        def display_signal_status(self, signal_status):
            SIGNAL_STATUS_TAB = const("")
            D7.on()
            print(f"{SIGNAL_STATUS_TAB}{signal_status}")
            D7.off()


######################### init main tasks
    TONE_GPIO = const(7) # the GPIO where DCF signal is received by MCU
    from DCF77.local_time_calendar_uGUI import LocalTimeCalendar
    display = DCF_Display_stub()
    local_timer = LocalTimeCalendar()
    DCF77_decoder = DCF_Decoder(TONE_GPIO, local_timer)


                
    def timer_IRQ(timer):
        timer_elapsed.set()
    
    async def time_trigger():
        while True:
            D0.off()
            await timer_elapsed.wait()
            D0.on()
            timer_elapsed.clear()
            local_timer.next_second()
            display.display_signal_status(DCF77_decoder.get_signal_status())
            display.display_time_status(DCF77_decoder.get_time_status())
            display.display_date_and_time(local_timer.get_raw_time_and_date())

    #################################################
    # triggering mechanism = 1-second internal timer
    timer = Timer(mode=Timer.PERIODIC, freq=1, callback=timer_IRQ)
    timer_elapsed = uasyncio.ThreadSafeFlag()
    #################################################
    
    #start coroutines
    scheduler = uasyncio.get_event_loop()

    scheduler.create_task(time_trigger())    
    scheduler.create_task(DCF77_decoder.DCF_signal_monitoring())
    scheduler.create_task(DCF77_decoder.frame_decoder())
    
    scheduler.run_forever()


