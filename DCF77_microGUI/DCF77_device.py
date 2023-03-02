import uasyncio as asyncio
from machine import Timer

from DCF77.decoder_uGUIv1 import *
from DCF77.local_time_calendar_uGUI import LocalTimeCalendar


class DCF_device():
    def __init__(self,key_in_gpio):
        self.local_time = LocalTimeCalendar()
        self.dcf_decoder = DCF_Decoder(key_in_gpio, self.local_time)
    
    def next_second(self):
        self.local_time.next_second()            
        
    def get_local_time(self):
        # Format:
        ## localtime : t[0]:year, t[1]:month, t[2]:mday, t[3]:hour, t[4]:minute, t[5]:second, t[6]:weekday, t[7]:time_zone
        return self.local_time.get_raw_time_and_date()
    
    def get_status(self):
        ts = self.dcf_decoder.get_time_status()
        time_state = ts[1]
        if ts[1] == SYNC:
            ts_text = "sync'd"
        elif time_state == SYNC_IN_PROGRESS:
            ts_text = "in progress"
        elif time_state == SYNC_FAILED:
            ts_text = "frame fail"
        elif time_state == OUT_OF_SYNC:
            ts_text = "out of sync"
        else:
            ts_text = "init"
        ss = self.dcf_decoder.get_signal_status()
        bit_rank = ss[0]
        last_bit = ss[1]
        return (ts_text,bit_rank,last_bit)
        # format
        ## time_status = [self._status_controller.time_event, self._status_controller.time_state, self._status_controller.error_message]
        ## signal_status  = [self._status_controller.last_received_frame_bit_rank, self._status_controller.last_received_frame_bit,
        ##                  self._status_controller.signal_event, self._status_controller.signal_state]


if __name__ == "__main__":
    
    # D0 = Probe(26) # -- time_trigger  
    # D1 = Probe(16) # DCF_Decoder._DCF_clock_IRQ_handler
    # D2 = Probe(17) # DCF_Decoder.frame_decoder
    # D3 = Probe(18) # 
    # D4 = Probe(19) # _StatusController.signal_received
    # D5 = Probe(20) # _StatusController.signal_timeout
    # D6 = Probe(21) # -- time_status == SYNC
    # D7 = Probe(27) #
    
    #--------------------------------------------------------------------------    
    TONE_GPIO = const(7) # the GPIO where DCF signal is received by MCU
    dcf = DCF_device(TONE_GPIO)    
    
    #--------------------------------------------------------------------------    
    def timer_IRQ(timer):
        one_second_time_event.set()

    async def time_trigger():
        while True:
            D0.off()
            await one_second_time_event.wait()
            D0.on()
            one_second_time_event.clear()
            dcf.local_time.next_second()
            print("\t"*5, dcf.get_local_time())
            print(dcf.get_status())

    Timer(mode=Timer.PERIODIC, freq=1, callback=timer_IRQ)
#         self.one_second_time_event = uasyncio.ThreadSafeFlag()
    one_second_time_event = uasyncio.ThreadSafeFlag()

    asyncio.create_task(dcf.dcf_decoder.DCF_signal_monitoring())
    asyncio.create_task(dcf.dcf_decoder.frame_decoder())
    asyncio.create_task(time_trigger())      
    scheduler = uasyncio.get_event_loop()
    scheduler.run_forever()


    
    

    
