#include "dram_controller.h"
#include <cstdlib>

// initialized in main.cc
uint32_t DRAM_MTPS, DRAM_DBUS_RETURN_TIME,
         tRP, tRCD, tCAS;


//Neelu: Adding variables for DRAM busy stats. 
//read_or_write only valid if channel busy is true. last_toggle_ccc contains the current_core_cycle of the last instant when channel_busy was modified. 
uint8_t channel_bank_busy[DRAM_CHANNELS] = {0}, read_or_write[DRAM_CHANNELS] = {0};
uint64_t last_bank_busy_ccc[DRAM_CHANNELS][NUM_CPUS] = {0}, last_bank_busy_cpu[DRAM_CHANNELS] = {0}, sum_cycles_read[DRAM_CHANNELS] = {0}, sum_cycles_write[DRAM_CHANNELS] = {0};

uint64_t banks_busy_read_cycles[DRAM_CHANNELS][DRAM_RANKS][DRAM_BANKS+1] = {0}, banks_busy_write_cycles[DRAM_CHANNELS][DRAM_RANKS][DRAM_BANKS+1] = {0};
//Neelu: Done adding variables for DRAM busy stats.


static int ideal_writes = -1;

static int no_idle_writes = -1;

static uint64_t cyc_total = 0, cyc_wq_nonempty = 0, cyc_rq_empty = 0, cyc_rqe_wqne = 0;
static uint64_t wq_occ_hist[DRAM_WQ_SIZE+1] = {0};
#define SERIES_INTERVAL 100000   
static uint64_t ser_idx = 0, ser_rd = 0, ser_rowmiss = 0, ser_last_wait = 0, ser_last_wr = 0;


static uint64_t wm_enter_forced = 0, wm_enter_idle = 0, wm_exit = 0;      
static uint64_t wm_cycles_reads_waiting = 0, wm_cycles_rq_empty = 0;      
static uint64_t rd_unsched_by_wm = 0, wr_unsched_by_rm = 0;              
static uint64_t wr_completed = 0, rd_completed = 0;
static uint64_t wr_in_episode[DRAM_CHANNELS] = {0};
static uint64_t wr_per_episode_hist[8] = {0};                            
static uint64_t rowmiss_cause[3] = {0,0,0};                               
static uint8_t  last_op_write[DRAM_CHANNELS][DRAM_RANKS][DRAM_BANKS];
static uint8_t  sched_cause[DRAM_CHANNELS][DRAM_RANKS][DRAM_BANKS];
static uint64_t rq_occ_hist[DRAM_RQ_SIZE+1] = {0};                       

static inline int wr_bucket(uint64_t n) { int b = 0; while (n > 0 && b < 7) { n >>= 1; b++; } return b; }


void MEMORY_CONTROLLER::reset_remain_requests(PACKET_QUEUE *queue, uint32_t channel)
{
    for (uint32_t i=0; i<queue->SIZE; i++) {
        if (queue->entry[i].scheduled) {

            uint64_t op_addr = queue->entry[i].address;
            uint32_t op_cpu = queue->entry[i].cpu,
                     op_channel = dram_get_channel(op_addr), 
                     op_rank = dram_get_rank(op_addr), 
                     op_bank = dram_get_bank(op_addr), 
                     op_row = dram_get_row(op_addr);

#ifdef DEBUG_PRINT
            //uint32_t op_column = dram_get_column(op_addr);
#endif

            // update open row
            if ((bank_request[op_channel][op_rank][op_bank].cycle_available - tCAS) <= current_core_cycle[op_cpu])
                bank_request[op_channel][op_rank][op_bank].open_row = op_row;
            else
                bank_request[op_channel][op_rank][op_bank].open_row = UINT32_MAX;

            // this bank is ready for another DRAM request
            bank_request[op_channel][op_rank][op_bank].request_index = -1;
            bank_request[op_channel][op_rank][op_bank].row_buffer_hit = 0;
            bank_request[op_channel][op_rank][op_bank].working = 0;
            bank_request[op_channel][op_rank][op_bank].cycle_available = current_core_cycle[op_cpu];
            if (bank_request[op_channel][op_rank][op_bank].is_write) {
                scheduled_writes[channel]--;
                bank_request[op_channel][op_rank][op_bank].is_write = 0;
            }
            else if (bank_request[op_channel][op_rank][op_bank].is_read) {
                scheduled_reads[channel]--;
                bank_request[op_channel][op_rank][op_bank].is_read = 0;
            }

            queue->entry[i].scheduled = 0;
            queue->entry[i].event_cycle = current_core_cycle[op_cpu];

            DP ( if (warmup_complete[op_cpu]) {
            cout << queue->NAME << " instr_id: " << queue->entry[i].instr_id << " swrites: " << scheduled_writes[channel] << " sreads: " << scheduled_reads[channel] << endl; });

        }
    }
    
    update_schedule_cycle(&RQ[channel]);
    update_schedule_cycle(&WQ[channel]);
    update_process_cycle(&RQ[channel]);
    update_process_cycle(&WQ[channel]);

#ifdef SANITY_CHECK
    if (queue->is_WQ) {
        if (scheduled_writes[channel] != 0)
            assert(0);
    }
    else {
        if (scheduled_reads[channel] != 0)
            assert(0);
    }
#endif
}

void MEMORY_CONTROLLER::operate()
{
	if (no_idle_writes < 0) { const char *e = getenv("DRAM_NO_IDLE_WRITES"); no_idle_writes = (e && e[0] == '1') ? 1 : 0; cout << "DRAM no_idle_writes=" << no_idle_writes << endl; }

	//Neelu: Capturing DRAM busy stats.
	if(all_warmup_complete >= NUM_CPUS)
	
	{	
		uint8_t bank_busy_in_this_iter = 0;
		for (uint32_t i=0; i<DRAM_CHANNELS; i++) {
			if(bank_busy_in_this_iter)
				break;
			for (uint32_t j=0; j<DRAM_RANKS; j++) {	
				if(bank_busy_in_this_iter)
					break;
				int num_of_banks_busy = 0;
				for (uint32_t k=0; k<DRAM_BANKS; k++) {
					if(bank_request[i][j][k].working)
					{
						num_of_banks_busy++;
					
						bank_busy_in_this_iter = 1;
						
						
					}
				}
				
				if(write_mode[i])
					banks_busy_write_cycles[i][j][num_of_banks_busy]++;
				else
					banks_busy_read_cycles[i][j][num_of_banks_busy]++;
			
			}
		}
			
	}

	


    for (uint32_t i=0; i<DRAM_CHANNELS; i++) {
        
      if ((write_mode[i] == 0) && ((WQ[i].occupancy >= DRAM_WRITE_HIGH_WM) || (!no_idle_writes && (RQ[i].occupancy == 0) && (WQ[i].occupancy > 0)))) { // use idle cycles to perform writes
            write_mode[i] = 1;

            
            if (all_warmup_complete >= NUM_CPUS) { if (WQ[i].occupancy >= DRAM_WRITE_HIGH_WM) wm_enter_forced++; else wm_enter_idle++; rd_unsched_by_wm += scheduled_reads[i]; wr_in_episode[i] = 0; }
            reset_remain_requests(&RQ[i], i);
            
            dbus_cycle_available[i] += DRAM_DBUS_TURN_AROUND_TIME;
        } else if (write_mode[i]) {

            if (WQ[i].occupancy == 0)
                write_mode[i] = 0;
            else if (RQ[i].occupancy && (WQ[i].occupancy < DRAM_WRITE_LOW_WM))
                write_mode[i] = 0;

            if (write_mode[i] == 0) {
             
                if (all_warmup_complete >= NUM_CPUS) { wm_exit++; wr_unsched_by_rm += scheduled_writes[i]; wr_per_episode_hist[wr_bucket(wr_in_episode[i])]++; }
                reset_remain_requests(&WQ[i], i);
               
                dbus_cycle_available[i] += DRAM_DBUS_TURN_AROUND_TIME;
            }
        }

        if (all_warmup_complete >= NUM_CPUS && write_mode[i]) { if (RQ[i].occupancy) wm_cycles_reads_waiting++; else wm_cycles_rq_empty++; }
        if (all_warmup_complete >= NUM_CPUS) { cyc_total++; if (WQ[i].occupancy) cyc_wq_nonempty++; if (!RQ[i].occupancy) { cyc_rq_empty++; if (WQ[i].occupancy) cyc_rqe_wqne++; } wq_occ_hist[WQ[i].occupancy > DRAM_WQ_SIZE ? DRAM_WQ_SIZE : WQ[i].occupancy]++; }
       
        if (write_mode[i] && (WQ[i].next_schedule_index < WQ[i].SIZE)) {
            if (WQ[i].next_schedule_cycle <= current_core_cycle[WQ[i].entry[WQ[i].next_schedule_index].cpu])
                schedule(&WQ[i]);
        }

       
        if (write_mode[i] && (WQ[i].next_process_index < WQ[i].SIZE)) {
            if (WQ[i].next_process_cycle <= current_core_cycle[WQ[i].entry[WQ[i].next_process_index].cpu])
                process(&WQ[i]);
        }

      
        if ((write_mode[i] == 0) && (RQ[i].next_schedule_index < RQ[i].SIZE)) {
            if (RQ[i].next_schedule_cycle <= current_core_cycle[RQ[i].entry[RQ[i].next_schedule_index].cpu])
                schedule(&RQ[i]);
        }

       
        if ((write_mode[i] == 0) && (RQ[i].next_process_index < RQ[i].SIZE)) {
            if (RQ[i].next_process_cycle <= current_core_cycle[RQ[i].entry[RQ[i].next_process_index].cpu])
                process(&RQ[i]);
        }
    }
}

void MEMORY_CONTROLLER::schedule(PACKET_QUEUE *queue)
{
    uint64_t read_addr;
    uint32_t read_channel, read_rank, read_bank, read_row;
    uint8_t  row_buffer_hit = 0;
    if (all_warmup_complete >= NUM_CPUS && !queue->is_WQ) { uint32_t o = queue->occupancy; rq_occ_hist[o > DRAM_RQ_SIZE ? DRAM_RQ_SIZE : o]++; }

    int oldest_index = -1;
    uint64_t oldest_cycle = UINT64_MAX;

  
    for (uint32_t i=0; i<queue->SIZE; i++) {

        if (queue->entry[i].scheduled) 
            continue;

        read_addr = queue->entry[i].address;
        if (read_addr == 0) 
            continue;

        read_channel = dram_get_channel(read_addr);
        read_rank = dram_get_rank(read_addr);
        read_bank = dram_get_bank(read_addr);

     
        if (bank_request[read_channel][read_rank][read_bank].working) { // should we check this or not? how do we know if bank is busy or not for all requests in the queue?

         
            continue;
        }

        read_row = dram_get_row(read_addr);
       
        if (bank_request[read_channel][read_rank][read_bank].open_row != read_row) {

           

            continue;
        }

        
        if (queue->entry[i].event_cycle < oldest_cycle) {
            oldest_cycle = queue->entry[i].event_cycle;
            oldest_index = i;
            row_buffer_hit = 1;
        }	  
    }

    if (oldest_index == -1) { 

        oldest_cycle = UINT64_MAX;
        for (uint32_t i=0; i<queue->SIZE; i++) {

           
            if (queue->entry[i].scheduled)
                continue;

        
            read_addr = queue->entry[i].address;
            if (read_addr == 0) 
                continue;

            read_channel = dram_get_channel(read_addr);
            read_rank = dram_get_rank(read_addr);
            read_bank = dram_get_bank(read_addr);
            if (bank_request[read_channel][read_rank][read_bank].working) 
                continue;

          
            if (queue->entry[i].event_cycle < oldest_cycle) {
                oldest_cycle = queue->entry[i].event_cycle;
                oldest_index = i;
            }
        }
    }

   
    if (oldest_index != -1) { 
        uint64_t LATENCY = 0;
        if (row_buffer_hit)  
            LATENCY = tCAS;
        else 
            LATENCY = tRP + tRCD + tCAS;

        uint64_t op_addr = queue->entry[oldest_index].address;
        uint32_t op_cpu = queue->entry[oldest_index].cpu,
                 op_channel = dram_get_channel(op_addr), 
                 op_rank = dram_get_rank(op_addr), 
                 op_bank = dram_get_bank(op_addr), 
                 op_row = dram_get_row(op_addr);
#ifdef DEBUG_PRINT
        uint32_t op_column = dram_get_column(op_addr);
#endif

     
        bank_request[op_channel][op_rank][op_bank].working = 1;
        bank_request[op_channel][op_rank][op_bank].working_type = queue->entry[oldest_index].type;
        if (all_warmup_complete >= NUM_CPUS && !queue->is_WQ && !row_buffer_hit)
            sched_cause[op_channel][op_rank][op_bank] = (bank_request[op_channel][op_rank][op_bank].open_row == UINT32_MAX) ? 0 : (last_op_write[op_channel][op_rank][op_bank] ? 1 : 2);
        last_op_write[op_channel][op_rank][op_bank] = queue->is_WQ ? 1 : 0;
        bank_request[op_channel][op_rank][op_bank].cycle_available = current_core_cycle[op_cpu] + LATENCY;

        bank_request[op_channel][op_rank][op_bank].request_index = oldest_index;
        bank_request[op_channel][op_rank][op_bank].row_buffer_hit = row_buffer_hit;
        if (queue->is_WQ) {
            bank_request[op_channel][op_rank][op_bank].is_write = 1;
            bank_request[op_channel][op_rank][op_bank].is_read = 0;
            scheduled_writes[op_channel]++;
        }
        else {
            bank_request[op_channel][op_rank][op_bank].is_write = 0;
            bank_request[op_channel][op_rank][op_bank].is_read = 1;
            scheduled_reads[op_channel]++;
        }

        bank_request[op_channel][op_rank][op_bank].open_row = op_row;

        queue->entry[oldest_index].scheduled = 1;
        queue->entry[oldest_index].event_cycle = current_core_cycle[op_cpu] + LATENCY;

        update_schedule_cycle(queue);
        update_process_cycle(queue);

        DP (if (warmup_complete[op_cpu]) {
        cout << "[" << queue->NAME << "] " <<  __func__ << " instr_id: " << queue->entry[oldest_index].instr_id;
        cout << " row buffer: " << (row_buffer_hit ? (int)bank_request[op_channel][op_rank][op_bank].open_row : -1) << hex;
        cout << " address: " << queue->entry[oldest_index].address << " full_addr: " << queue->entry[oldest_index].full_addr << dec;
        cout << " index: " << oldest_index << " occupancy: " << queue->occupancy;
        cout << " ch: " << op_channel << " rank: " << op_rank << " bank: " << op_bank; // wrong from here
        cout << " row: " << op_row << " col: " << op_column;
        cout << " current: " << current_core_cycle[op_cpu] << " event: " << queue->entry[oldest_index].event_cycle << endl; });
    }
}

void MEMORY_CONTROLLER::process(PACKET_QUEUE *queue)
{
    uint32_t request_index = queue->next_process_index;

    if (request_index == queue->SIZE)
        assert(0);

    uint8_t  op_type = queue->entry[request_index].type;
    uint64_t op_addr = queue->entry[request_index].address;
    uint32_t op_cpu = queue->entry[request_index].cpu,
             op_channel = dram_get_channel(op_addr), 
             op_rank = dram_get_rank(op_addr), 
             op_bank = dram_get_bank(op_addr);
#ifdef DEBUG_PRINT
    uint32_t op_row = dram_get_row(op_addr), 
             op_column = dram_get_column(op_addr);
#endif

    if (bank_request[op_channel][op_rank][op_bank].request_index != (int)request_index) {
        assert(0);
    }

  
    if (bank_request[op_channel][op_rank][op_bank].cycle_available <= current_core_cycle[op_cpu]) {

        
        if (dbus_cycle_available[op_channel] <= current_core_cycle[op_cpu]) {

            if (queue->is_WQ) {
                
                dbus_cycle_available[op_channel] = current_core_cycle[op_cpu] + DRAM_DBUS_RETURN_TIME;

                if (bank_request[op_channel][op_rank][op_bank].row_buffer_hit)
                    queue->ROW_BUFFER_HIT++;
                else
                    queue->ROW_BUFFER_MISS++;

              
                bank_request[op_channel][op_rank][op_bank].request_index = -1;
                bank_request[op_channel][op_rank][op_bank].row_buffer_hit = 0;
                bank_request[op_channel][op_rank][op_bank].working = false;
                bank_request[op_channel][op_rank][op_bank].is_write = 0;
                bank_request[op_channel][op_rank][op_bank].is_read = 0;

                if (all_warmup_complete >= NUM_CPUS) { wr_completed++; wr_in_episode[op_channel]++; }
                scheduled_writes[op_channel]--;
            } else {
               
                dbus_cycle_available[op_channel] = current_core_cycle[op_cpu] + DRAM_DBUS_RETURN_TIME;
                queue->entry[request_index].event_cycle = dbus_cycle_available[op_channel]; 

                DP ( if (warmup_complete[op_cpu]) {
                cout << "[" << queue->NAME << "] " <<  __func__ << " return data" << hex;
                cout << " address: " << queue->entry[request_index].address << " full_addr: " << queue->entry[request_index].full_addr << dec;
                cout << " occupancy: " << queue->occupancy << " channel: " << op_channel << " rank: " << op_rank << " bank: " << op_bank;
                cout << " row: " << op_row << " column: " << op_column;
                cout << " current_cycle: " << current_core_cycle[op_cpu] << " event_cycle: " << queue->entry[request_index].event_cycle << endl; });

               
                if (all_warmup_complete >= NUM_CPUS) { rd_completed++; ser_rd++; if (!bank_request[op_channel][op_rank][op_bank].row_buffer_hit) { rowmiss_cause[sched_cause[op_channel][op_rank][op_bank]]++; ser_rowmiss++; }
                  if (ser_rd == SERIES_INTERVAL) { cout << "WMSERIES " << ser_idx++ << " " << current_core_cycle[0] << " " << ser_rd << " " << ser_rowmiss << " " << (wm_cycles_reads_waiting - ser_last_wait) << " " << (wr_completed - ser_last_wr) << endl; ser_last_wait = wm_cycles_reads_waiting; ser_last_wr = wr_completed; ser_rd = 0; ser_rowmiss = 0; } }
                upper_level_dcache[op_cpu]->return_data(&queue->entry[request_index]);

                if (bank_request[op_channel][op_rank][op_bank].row_buffer_hit)
                    queue->ROW_BUFFER_HIT++;
                else
                    queue->ROW_BUFFER_MISS++;

                bank_request[op_channel][op_rank][op_bank].request_index = -1;
                bank_request[op_channel][op_rank][op_bank].row_buffer_hit = 0;
                bank_request[op_channel][op_rank][op_bank].working = false;
                bank_request[op_channel][op_rank][op_bank].is_write = 0;
                bank_request[op_channel][op_rank][op_bank].is_read = 0;

                scheduled_reads[op_channel]--;
            }

           
            queue->remove_queue(&queue->entry[request_index]);
            update_process_cycle(queue);
        }
        else { 

#if 0
          
            if ((op_type == PREFETCH) || (op_type == LOAD)) {
              

              
                upper_level_dcache[op_cpu]->return_data(&queue->entry[request_index]);

                if (bank_request[op_channel][op_rank][op_bank].row_buffer_hit)
                    queue->ROW_BUFFER_HIT++;
                else
                    queue->ROW_BUFFER_MISS++;

              
                bank_request[op_channel][op_rank][op_bank].request_index = -1;
                bank_request[op_channel][op_rank][op_bank].row_buffer_hit = 0;
                bank_request[op_channel][op_rank][op_bank].working = false;
                bank_request[op_channel][op_rank][op_bank].is_write = 0;
                bank_request[op_channel][op_rank][op_bank].is_read = 0;

                scheduled_reads[op_channel]--;

                
                queue->remove_queue(&queue->entry[request_index]);
                update_process_cycle(queue);

                return;
            }
#endif

            dbus_cycle_congested[op_channel] += (dbus_cycle_available[op_channel] - current_core_cycle[op_cpu]);
            bank_request[op_channel][op_rank][op_bank].cycle_available = dbus_cycle_available[op_channel];
            dbus_congested[NUM_TYPES][NUM_TYPES]++;
            dbus_congested[NUM_TYPES][op_type]++;
            dbus_congested[bank_request[op_channel][op_rank][op_bank].working_type][NUM_TYPES]++;
            dbus_congested[bank_request[op_channel][op_rank][op_bank].working_type][op_type]++;

            DP ( if (warmup_complete[op_cpu]) {
            cout << "[" << queue->NAME << "] " <<  __func__ << " dbus_occupied" << hex;
            cout << " address: " << queue->entry[request_index].address << " full_addr: " << queue->entry[request_index].full_addr << dec;
            cout << " occupancy: " << queue->occupancy << " channel: " << op_channel << " rank: " << op_rank << " bank: " << op_bank;
            cout << " row: " << op_row << " column: " << op_column;
            cout << " current_cycle: " << current_core_cycle[op_cpu] << " event_cycle: " << bank_request[op_channel][op_rank][op_bank].cycle_available << endl; });
        }
    }
}

int MEMORY_CONTROLLER::add_rq(PACKET *packet)
{
    
    if (all_warmup_complete < NUM_CPUS) {
        if (packet->instruction) 
            upper_level_icache[packet->cpu]->return_data(packet);
        else 
            upper_level_dcache[packet->cpu]->return_data(packet);

        return -1;
    }

   
    uint32_t channel = dram_get_channel(packet->address);
    int wq_index = check_dram_queue(&WQ[channel], packet);
    if (wq_index != -1) {
        
   

            packet->data = WQ[channel].entry[wq_index].data;
            if (packet->instruction) 
                upper_level_icache[packet->cpu]->return_data(packet);
            else // data
                upper_level_dcache[packet->cpu]->return_data(packet);
     

        DP ( if (packet->cpu) {
        cout << "[" << NAME << "_RQ] " << __func__ << " instr_id: " << packet->instr_id << " found recent writebacks";
        cout << hex << " read: " << packet->address << " writeback: " << WQ[channel].entry[wq_index].address << dec << endl; });

        ACCESS[1]++;
        HIT[1]++;

        WQ[channel].FORWARD++;
        RQ[channel].ACCESS++;
        

        return -1;
    }

  
    int index = check_dram_queue(&RQ[channel], packet);
    if (index != -1)
        return index; // merged index

   
    for (index=0; index<DRAM_RQ_SIZE; index++) {
        if (RQ[channel].entry[index].address == 0) {
            
            RQ[channel].entry[index] = *packet;
            RQ[channel].occupancy++;

#ifdef DEBUG_PRINT
            uint32_t channel = dram_get_channel(packet->address),
                     rank = dram_get_rank(packet->address),
                     bank = dram_get_bank(packet->address),
                     row = dram_get_row(packet->address),
                     column = dram_get_column(packet->address); 
#endif

#ifdef PRINT_QUEUE_TRACE
           if(packet->instr_id == QTRACE_INSTR_ID)
            {
            uint32_t channel = dram_get_channel(packet->address),
                     rank = dram_get_rank(packet->address),
                     bank = dram_get_bank(packet->address),
                     row = dram_get_row(packet->address),
                     column = dram_get_column(packet->address);
            cout << "[" << NAME << "_RQ] " <<  __func__ << " instr_id: " << packet->instr_id << " address: " << hex << packet->address;
            cout << " full_addr: " << packet->full_addr << dec << " ch: " << channel;
            cout << " rank: " << rank << " bank: " << bank << " row: " << row << " col: " << column;
            cout << " occupancy: " << RQ[channel].occupancy << " current: " << current_core_cycle[packet->cpu] << " event: " << packet->event_cycle << " cpu: "<<packet->cpu<<endl;
    }
#endif


            DP ( if(warmup_complete[packet->cpu]) {
            cout << "[" << NAME << "_RQ] " <<  __func__ << " instr_id: " << packet->instr_id << " address: " << hex << packet->address;
            cout << " full_addr: " << packet->full_addr << dec << " ch: " << channel;
            cout << " rank: " << rank << " bank: " << bank << " row: " << row << " col: " << column;
            cout << " occupancy: " << RQ[channel].occupancy << " current: " << current_core_cycle[packet->cpu] << " event: " << packet->event_cycle << endl; });

            break;
        }
    }

    update_schedule_cycle(&RQ[channel]);

    return -1;
}

int MEMORY_CONTROLLER::add_wq(PACKET *packet)
{
    
    if (all_warmup_complete < NUM_CPUS)
        return -1;

        if (ideal_writes < 0) { const char *e = getenv("IDEAL_DRAM_WRITES"); ideal_writes = (e && e[0] == '1') ? 1 : 0; cout << "DRAM ideal_writes=" << ideal_writes << endl; }
    if (ideal_writes) return -1;   // ablation: writes are free
    // check for duplicates in the write queue
    uint32_t channel = dram_get_channel(packet->address);
    int index = check_dram_queue(&WQ[channel], packet);
    if (index != -1)
        return index; 

    
    for (index=0; index<DRAM_WQ_SIZE; index++) {
        if (WQ[channel].entry[index].address == 0) {
            
            WQ[channel].entry[index] = *packet;
            WQ[channel].occupancy++;

#ifdef DEBUG_PRINT
            uint32_t channel = dram_get_channel(packet->address),
                     rank = dram_get_rank(packet->address),
                     bank = dram_get_bank(packet->address),
                     row = dram_get_row(packet->address),
                     column = dram_get_column(packet->address); 
#endif


#ifdef PRINT_QUEUE_TRACE
            if(packet->instr_id == QTRACE_INSTR_ID)
            {
            uint32_t channel = dram_get_channel(packet->address),
                     rank = dram_get_rank(packet->address),
                     bank = dram_get_bank(packet->address),
                     row = dram_get_row(packet->address),
                     column = dram_get_column(packet->address);
                  cout << "[" << NAME << "_WQ] " <<  __func__ << " instr_id: " << packet->instr_id << " address: " << hex << packet->address;
            cout << " full_addr: " << packet->full_addr << dec << " ch: " << channel;
            cout << " rank: " << rank << " bank: " << bank << " row: " << row << " col: " << column;
            cout << " occupancy: " << WQ[channel].occupancy << " current: " << current_core_cycle[packet->cpu] << " event: " << packet->event_cycle << " cpu: "<<packet->cpu<<endl;
    }
#endif


            DP ( if(warmup_complete[packet->cpu]) {
            cout << "[" << NAME << "_WQ] " <<  __func__ << " instr_id: " << packet->instr_id << " address: " << hex << packet->address;
            cout << " full_addr: " << packet->full_addr << dec << " ch: " << channel;
            cout << " rank: " << rank << " bank: " << bank << " row: " << row << " col: " << column;
            cout << " occupancy: " << WQ[channel].occupancy << " current: " << current_core_cycle[packet->cpu] << " event: " << packet->event_cycle << endl; });

            break;
        }
    }

    update_schedule_cycle(&WQ[channel]);

    return -1;
}

int MEMORY_CONTROLLER::add_pq(PACKET *packet)
{
    return -1;
}

void MEMORY_CONTROLLER::return_data(PACKET *packet)
{

}

void MEMORY_CONTROLLER::update_schedule_cycle(PACKET_QUEUE *queue)
{

    uint64_t min_cycle = UINT64_MAX;
    uint32_t min_index = queue->SIZE;
    for (uint32_t i=0; i<queue->SIZE; i++) {
      

        if (queue->entry[i].address && (queue->entry[i].scheduled == 0) && (queue->entry[i].event_cycle < min_cycle)) {
            min_cycle = queue->entry[i].event_cycle;
            min_index = i;
        }
    }
    
    queue->next_schedule_cycle = min_cycle;
    queue->next_schedule_index = min_index;
    if (min_index < queue->SIZE) {

        DP (if (warmup_complete[queue->entry[min_index].cpu]) {
        cout << "[" << queue->NAME << "] " <<  __func__ << " instr_id: " << queue->entry[min_index].instr_id;
        cout << " address: " << hex << queue->entry[min_index].address << " full_addr: " << queue->entry[min_index].full_addr;
        cout << " data: " << queue->entry[min_index].data << dec;
        cout << " event: " << queue->entry[min_index].event_cycle << " current: " << current_core_cycle[queue->entry[min_index].cpu] << " next: " << queue->next_schedule_cycle << endl; });
    }
}

void MEMORY_CONTROLLER::update_process_cycle(PACKET_QUEUE *queue)
{
  
    uint64_t min_cycle = UINT64_MAX;
    uint32_t min_index = queue->SIZE;
    for (uint32_t i=0; i<queue->SIZE; i++) {
        if (queue->entry[i].scheduled && (queue->entry[i].event_cycle < min_cycle)) {
            min_cycle = queue->entry[i].event_cycle;
            min_index = i;
        }
    }
    
    queue->next_process_cycle = min_cycle;
    queue->next_process_index = min_index;
    if (min_index < queue->SIZE) {

        DP (if (warmup_complete[queue->entry[min_index].cpu]) {
        cout << "[" << queue->NAME << "] " <<  __func__ << " instr_id: " << queue->entry[min_index].instr_id;
        cout << " address: " << hex << queue->entry[min_index].address << " full_addr: " << queue->entry[min_index].full_addr;
        cout << " data: " << queue->entry[min_index].data << dec << " num_returned: " << queue->num_returned;
        cout << " event: " << queue->entry[min_index].event_cycle << " current: " << current_core_cycle[queue->entry[min_index].cpu] << " next: " << queue->next_process_cycle << endl; });
    }
}

int MEMORY_CONTROLLER::check_dram_queue(PACKET_QUEUE *queue, PACKET *packet)
{
    
    for (uint32_t index=0; index<queue->SIZE; index++) {
        if (queue->entry[index].address == packet->address) {
            
            DP ( if (warmup_complete[packet->cpu]) {
            cout << "[" << queue->NAME << "] " << __func__ << " same entry instr_id: " << packet->instr_id << " prior_id: " << queue->entry[index].instr_id;
            cout << " address: " << hex << packet->address << " full_addr: " << packet->full_addr << dec << endl; });

            return index;
        }
    }

    DP ( if (warmup_complete[packet->cpu]) {
    cout << "[" << queue->NAME << "] " << __func__ << " new address: " << hex << packet->address;
    cout << " full_addr: " << packet->full_addr << dec << endl; });

    DP ( if (warmup_complete[packet->cpu] && (queue->occupancy == queue->SIZE)) {
    cout << "[" << queue->NAME << "] " << __func__ << " mshr is full";
    cout << " instr_id: " << packet->instr_id << " mshr occupancy: " << queue->occupancy;
    cout << " address: " << hex << packet->address;
    cout << " full_addr: " << packet->full_addr << dec;
    cout << " cycle: " << current_core_cycle[packet->cpu] << endl; });

    return -1;
}

uint32_t MEMORY_CONTROLLER::dram_get_channel(uint64_t address)
{
    if (LOG2_DRAM_CHANNELS == 0)
        return 0;

    int shift = 0;

    return (uint32_t) (address >> shift) & (DRAM_CHANNELS - 1);
}

uint32_t MEMORY_CONTROLLER::dram_get_bank(uint64_t address)
{
    if (LOG2_DRAM_BANKS == 0)
        return 0;

    int shift = LOG2_DRAM_CHANNELS;

    return (uint32_t) (address >> shift) & (DRAM_BANKS - 1);
}

uint32_t MEMORY_CONTROLLER::dram_get_column(uint64_t address)
{
    if (LOG2_DRAM_COLUMNS == 0)
        return 0;

    int shift = LOG2_DRAM_BANKS + LOG2_DRAM_CHANNELS;

    return (uint32_t) (address >> shift) & (DRAM_COLUMNS - 1);
}

uint32_t MEMORY_CONTROLLER::dram_get_rank(uint64_t address)
{
    if (LOG2_DRAM_RANKS == 0)
        return 0;

    int shift = LOG2_DRAM_COLUMNS + LOG2_DRAM_BANKS + LOG2_DRAM_CHANNELS;

    return (uint32_t) (address >> shift) & (DRAM_RANKS - 1);
}

uint32_t MEMORY_CONTROLLER::dram_get_row(uint64_t address)
{
    if (LOG2_DRAM_ROWS == 0)
        return 0;

    int shift = LOG2_DRAM_RANKS + LOG2_DRAM_COLUMNS + LOG2_DRAM_BANKS + LOG2_DRAM_CHANNELS;

    return (uint32_t) (address >> shift) & (DRAM_ROWS - 1);
}

uint32_t MEMORY_CONTROLLER::get_occupancy(uint8_t queue_type, uint64_t address)
{
    uint32_t channel = dram_get_channel(address);
    if (queue_type == 1)
        return RQ[channel].occupancy;
    else if (queue_type == 2)
        return WQ[channel].occupancy;

    return 0;
}

uint32_t MEMORY_CONTROLLER::get_size(uint8_t queue_type, uint64_t address)
{
    uint32_t channel = dram_get_channel(address);
    if (queue_type == 1)
        return RQ[channel].SIZE;
    else if (queue_type == 2)
        return WQ[channel].SIZE;

    return 0;
}

void MEMORY_CONTROLLER::increment_WQ_FULL(uint64_t address)
{
    uint32_t channel = dram_get_channel(address);
    WQ[channel].FULL++;
}

void MEMORY_CONTROLLER::print_DRAM_busy_stats()
{
	cout << " All warmup complete: " << unsigned(all_warmup_complete) << endl;
	cout << "WMSTAT write_mode_enter_forced(WQ>=high_wm): " << wm_enter_forced << "  enter_idle(RQ empty): " << wm_enter_idle << "  exits: " << wm_exit << endl;
	cout << "WMSTAT write_mode_cycles_reads_waiting: " << wm_cycles_reads_waiting << "  write_mode_cycles_RQ_empty: " << wm_cycles_rq_empty << endl;
	cout << "WMSTAT reads_unscheduled_at_enter: " << rd_unsched_by_wm << "  writes_unscheduled_at_exit: " << wr_unsched_by_rm << endl;
	cout << "WMSTAT reads_completed: " << rd_completed << "  writes_completed: " << wr_completed << endl;
	cout << "WMSTAT writes_per_episode_hist[0,1,2-3,4-7,8-15,16-31,32-63,64+]:";
	for (int b = 0; b < 8; b++) cout << " " << wr_per_episode_hist[b];
	cout << endl;
	cout << "WMSTAT read_rowmiss_cause closed/invalid: " << rowmiss_cause[0] << "  bank_last_used_by_write: " << rowmiss_cause[1] << "  read_read_conflict: " << rowmiss_cause[2] << endl;
	cout << "WMSTAT cycles total: " << cyc_total << "  WQ_nonempty: " << cyc_wq_nonempty << "  RQ_empty: " << cyc_rq_empty << "  RQ_empty_and_WQ_nonempty: " << cyc_rqe_wqne << endl;
	cout << "WMSTAT WQ_occupancy_hist[0..64]:";
	for (uint32_t b = 0; b <= DRAM_WQ_SIZE; b++) cout << " " << wq_occ_hist[b];
	cout << endl;
	cout << "WMSTAT RQ_depth_at_read_schedule_hist[0..64]:";
	for (uint32_t b = 0; b <= DRAM_RQ_SIZE; b++) cout << " " << rq_occ_hist[b];
	cout << endl;
	for(uint32_t i = 0; i < DRAM_CHANNELS; i++)
	{
		cout << "Channel " << i << " Bank busy for read cycles: " << sum_cycles_read[i] << endl;
		cout << "Channel " << i << " Bank busy for write cycles: " << sum_cycles_write[i] << endl;
	}

	for(uint32_t i = 0; i < DRAM_CHANNELS; i++)
	{
		cout << "Channel " << i << endl;
		for(uint32_t j = 0; j < DRAM_RANKS; j++)
		{
			cout << "Rank " << j << endl;
			for(uint32_t k = 0; k <= DRAM_BANKS; k++)
			{
				cout << k << "banks busy for read cycles: " << banks_busy_read_cycles[i][j][k] << endl;
				cout << k << "banks busy for write cycles: " << banks_busy_write_cycles[i][j][k] << endl;
			}
		}
	}
}