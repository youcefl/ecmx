# ----------------------------------------------------------------------------
# The MIT License (MIT)
#
# Copyright (c) 2016 Youcef Lemsafer
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
# ----------------------------------------------------------------------------

# ----------------------------------------------------------------------------
# Creation date: 2014.05.22
# Creator: Youcef Lemsafer
# What it is: a wrapper over GMP-ECM which allows running multiple instances
# of it in parallel. The number of instances to run in parallel is specified
# via command line option -t (--threads).
# ----------------------------------------------------------------------------

import argparse
import threading
import subprocess
import logging
import time
import queue
import os
from datetime import datetime


# ----------------------------------------------------------------------------
# ----------------------------------------------------------------------------
VERSION = '0.4.1'
NAME = 'ecmx'
print( NAME + ' version ' + VERSION )
print( 'Copyright Youcef Lemsafer (May 2014 - Jan 2016).' )

# ----------------------------------------------------------------------------
# ----------------------------------------------------------------------------
logger = logging.getLogger(NAME)
logger.setLevel(logging.DEBUG)


# ----------------------------------------------------------------------------
# Command line definition
# ----------------------------------------------------------------------------
cmd_line_parser = argparse.ArgumentParser()
cmd_line_parser.add_argument( '-v', '--verbosity', action = 'count',
                              default = 0,
                              help = 'Increase verbosity level.' )
cmd_line_parser.add_argument( '-t', '--threads', required = True, type = int,
                              help = 'Number of threads.' )
cmd_line_parser.add_argument( '-d', '--delta_progress', required = False, type = int,
                              default = 600, # ten minutes
                              help = 'The number of seconds between progress outputs.')
cmd_line_parser.add_argument( '-q', '--quiet', required = False, action = 'store_true',
                              help = 'Make GMP-ECM less verbose.' )
cmd_line_parser.add_argument( '-maxmem', '--max_memory',
                              help = 'Maximum memory usage per thread.' )
cmd_line_parser.add_argument( '-k', '--stage2_steps',
                              type = int, required = False,
                              help = 'Number of steps to perform in stage 2.' )
cmd_line_parser.add_argument( '-n', '--nice', required = False, action = 'store_true',
                              help = 'Run ecm in "nice" mode (below normal priority).' )
cmd_line_parser.add_argument( '-nn', '--very_nice', required = False, action = 'store_true',
                              help = 'Run ecm in "very nice" mode (idle priority).' )
cmd_line_parser.add_argument( '-i', '--input_file', required = True,
                              help = 'Input file.' )
cmd_line_parser.add_argument( '-o', '--output_path', required = True,
                              help = 'Output file path.' )
cmd_line_parser.add_argument( '-e', '--ecm_path', default = 'ecm',
                              help = 'Path of ecm executable.' )
cmd_line_parser.add_argument( '-cs', '--curves_spec', required = True,
                              nargs = 2, help = 'Curves specification as <number of curves> <B1> ('
                              + 'the option can be specified multiple times e.g. -cs 960 1e6 -cs 2400 3e6).',
                              action = 'append',
                              metavar = ('NUMBER_OF_CURVES', 'B1') )
arguments = cmd_line_parser.parse_args()


# ----------------------------------------------------------------------------
# ----------------------------------------------------------------------------
def string_array_to_string(str_array):
    str = ''
    is_first = True
    sep = ''
    for s in str_array:
        str += sep
        str += s
        if( not sep ):
            sep = ' '
    return str


# ----------------------------------------------------------------------------
# ----------------------------------------------------------------------------
class EcmWorkUnit:
    """Holds parameters defining a work unit (number of curves, B1, etc.)"""

    # ----------------------------------------------------------------------------
    # ----------------------------------------------------------------------------
    def __init__(self, args, curves, B1, id, fully_factored_event):
        self.args = args # command line arguments
        self.curves = curves # number of curves to run
        self.B1 = B1
        self.id = id
        self.fully_factored_event = fully_factored_event
        self.return_code = -1
        self.factor_found = False
        self.output_file_path = args.output_path + \
                                    '-ecmx.{0:s}.out'.format(id)
        self.processed = False
        self.thread_id = 0
        # Note: my_curves_done doesn't have to be protected from
        # concurrent access because work units are not shared
        # between workers and the number of curves done from
        # each work unit is only ever read at the end when
        # the workers are done.
        self.my_curves_done = 0

    # ----------------------------------------------------------------------------
    # ----------------------------------------------------------------------------
    def inc_curves_done(self):
        """Increments the number of curves done by one."""

        self.my_curves_done = self.my_curves_done + 1

    # ----------------------------------------------------------------------------
    # ----------------------------------------------------------------------------
    def curves_done(self):
        """Returns the number of curves performed"""

        return self.my_curves_done


# ----------------------------------------------------------------------------
# ----------------------------------------------------------------------------
class EcmWorker:
    """Class defining worker threads

    Once method start is called on an instance of this class
    it keeps consuming work units from the work queue and running
    their processing until there is no more work or the number
    is fully factored.
    """

    id_seq = 1 # sequence for thread ids

    # ----------------------------------------------------------------------------
    # ----------------------------------------------------------------------------
    def __init__(self, work_queue, no_more_work_event, fully_factored_event, id, timer):
        self.work_queue = work_queue
        self.no_more_work_event = no_more_work_event
        self.fully_factored_event = fully_factored_event
        self.thread = threading.Thread( target = self.work, args=() )
        self.id = id
        self.id_seq = self.id_seq + 1
        self.timer = timer
        self.lastCurveOutput = ''
        self.lastCurveOutputPrefix = ''
        self.outputLastCurveIndic = -1
        self.gmpEcmOutputHasTimestamp = False

    
    # ----------------------------------------------------------------------------
    # ----------------------------------------------------------------------------
    def work(self):
        """Loops getting work units from the queue and running their processing"""

        while(True):
            try:
                work_unit = self.work_queue.get_nowait()
                work_unit.thread_id = self.id
                self.do_run_ecm(work_unit)
            except queue.Empty:
                if(  self.no_more_work_event.is_set() 
                  or self.fully_factored_event.is_set() ):
                    break
                time.sleep(1)
                continue

    # ----------------------------------------------------------------------------
    # ----------------------------------------------------------------------------
    def start(self):
        self.thread.start()

    # ----------------------------------------------------------------------------
    # ----------------------------------------------------------------------------
    def join(self):
        self.thread.join()

    # ----------------------------------------------------------------------------
    # ----------------------------------------------------------------------------
    def build_gmp_ecm_cmd_line(self, work_unit):
        """Returns GMP-ECM command line for a given work unit"""

        args = work_unit.args
        cmd = []
        cmd.append(args.ecm_path)
        if( not args.quiet ):
            cmd.append('-v')
            cmd.append('-timestamp')
        if( args.nice ):
            cmd.append('-n')
        if( args.very_nice ):
            cmd.append('-nn')
        cmd.append('-inp')
        cmd.append('{0:s}'.format(args.input_file))
        if (args.max_memory):
            cmd.append('-maxmem')
            cmd.append('{0:s}'.format(args.max_memory))
        if (args.stage2_steps):
            cmd.append('-k')
            cmd.append(str(args.stage2_steps))
        cmd.append('-c')
        cmd.append('{0:d}'.format(work_unit.curves))
        cmd.append('{0:s}'.format(work_unit.B1))

        return cmd


    # ----------------------------------------------------------------------------
    # ----------------------------------------------------------------------------
    def do_run_ecm(self, work_unit):
        """Processes a work unit"""

        # don't bother running a work unit if the number is fully factored
        if( work_unit.fully_factored_event.is_set() ): 
            return
        cmd = self.build_gmp_ecm_cmd_line(work_unit)
        output_file_path = work_unit.output_file_path
        with open(output_file_path, 'ab') as output_f, open(output_file_path, 'r') as output_r:
            # Reader has to ignore any previous file content
            output_r.seek(0, os.SEEK_END)
            logger.info('Running {0:d} curves at {1:s} (thread {2:d})...'.format(work_unit.curves,
                            work_unit.B1, work_unit.thread_id))
            proc = subprocess.Popen(cmd, bufsize = 0, stdout = output_f, stderr = output_f)
            self.timer.on_work_unit_started(work_unit)
            logger.debug('[pid: {0:d}] '.format(proc.pid) + string_array_to_string(cmd)
                             + ' > {0:s} 2>&1'.format(output_file_path))
            haveToLeave = False
            self.clear_parsing_data()

            while(True):
                if( proc.poll() != None ):
                    work_unit.return_code = proc.returncode
                    # Bit 3 is set when cofactor is PRP, return code is 8 when
                    # the input number itself is found as factor
                    if( (work_unit.return_code & 8) and (work_unit.return_code != 8) ):
                        logger.info('A factor has been found (thread {0:d}), the cofactor is PRP!'.format(self.id))
                        logger.debug('Factor found by [pid:{0:d}], cofactor is PRP.'.format(proc.pid))
                        work_unit.fully_factored_event.set()
                        work_unit.factor_found = True
                    elif( work_unit.return_code & 2 ):
                        logger.info('A factor has been found (thread {0:d})!'.format(self.id))
                        logger.debug('Factor found by [pid:{0:d}].'.format(proc.pid))
                        work_unit.factor_found = True
                    haveToLeave = True
                else:
                    if( work_unit.fully_factored_event.is_set() ):
                        proc.kill()
                        haveToLeave = True
                self.parse_gmp_ecm_output(work_unit, output_r)
                if(haveToLeave):
                    break
                time.sleep(2)

            logger.debug('Work unit {0:s} processed.'.format(work_unit.id))
            work_unit.processed = True


    # ----------------------------------------------------------------------------
    # ----------------------------------------------------------------------------
    def clear_parsing_data(self):
        """Resets GMP-ECM output parsing data"""

        self.lastCurveOutput = ''
        self.lastCurveOutputPrefix = ''
        self.outputLastCurveIndic = -1
        self.gmpEcmOutputHasTimestamp = False


    # ----------------------------------------------------------------------------
    # ----------------------------------------------------------------------------
    def parse_gmp_ecm_output(self, work_unit, output_r):
        """"Parses" GMP-ECM's output to extract needed information

        Lines of interest are the following ones:
          - 'GMP-ECM <version number> ...' => first line printed by GMP-ECM, has
            to be added to the prefix
          - '[Sat Jan 16 ...]' => timestamp indicating that a new curve is being done
          - 'Using B1=...' => in case the timestamp is not present this indicates start
            of a new curve
          - 'Input number is <number>' => has to be added to the prefix   
          - 'Running on <machine name>' => has to be added to the prefix
          - 'Step 2 took ' => indicates curve done (won't be there if a factor is found
            in step 1)
          - '********** Factor found in step 1' => indicates curve done
        When a factor is found we have to print GMP-ECM's output regarding last curve
        and when doing so don't forget the last two lines:
          ********** Factor found in step ....
          Found ....                                               # this one...
          <Composite|Probable prime> cofactor ... has x digits     # and this one
        """

        for line in output_r:
            if(line.startswith('GMP-ECM ')):
                self.lastCurveOutputPrefix = line
                self.lastCurveOutput = ''
                continue
            if(line.startswith(('Running on', 'Input number'))):
                self.lastCurveOutputPrefix = self.lastCurveOutputPrefix + line
                continue
            if(line.startswith('[')):
                self.lastCurveOutput = line
                self.gmpEcmOutputHasTimestamp = True
                continue
            if(line.startswith('Using B1=')):
                if(not self.gmpEcmOutputHasTimestamp):
                    self.lastCurveOutput = ''
                self.gmpEcmOutputHasTimestamp = False
            if(line.startswith(('Step 2 took ', '********** Factor found in step 1'))):
                self.timer.curve_done(work_unit.B1)
                work_unit.inc_curves_done()
            if(line.startswith('********** Factor found')):
                self.outputLastCurveIndic = 0
            self.lastCurveOutput = self.lastCurveOutput + line
            if(self.outputLastCurveIndic >= 0):
                self.outputLastCurveIndic = self.outputLastCurveIndic + 1
            if(self.outputLastCurveIndic == 3):
                logger.info('GMP-ECM output (thread {0:d}):\n\n'.format(self.id) 
                             + self.lastCurveOutputPrefix + self.lastCurveOutput)
                self.outputLastCurveIndic = -1


# ----------------------------------------------------------------------------
# ----------------------------------------------------------------------------
class Timer:
    """Timer class, outputs progress, elapsed time, average curve duration, etc."""

    # ----------------------------------------------------------------------------
    # ----------------------------------------------------------------------------
    def __init__(self, work_units, seconds_between_output):
        self.time_table = dict(dict())
        self.time_table_lck = threading.Lock()
        for wk in work_units:
            self.time_table[wk.B1] =  { 'curvesDone' : 0,
                'curves' : (self.time_table[wk.B1]['curves'] + wk.curves) if (wk.B1 in self.time_table) else wk.curves,
                'isStarted' : False,
                'startTime' : datetime.min,
                'Done' : False}
        self.thread = threading.Thread(target = self.work, args=())
        self.end_event = threading.Event()
        self.seconds_between_output = seconds_between_output


    # ----------------------------------------------------------------------------
    # ----------------------------------------------------------------------------
    def work(self):
        logger.debug('Starting timer...')
        lastOuputTime = datetime.now()
        while(True):
            with self.time_table_lck:
                for B1, B1Info in self.time_table.items():
                    if(B1Info['Done']):
                        continue
                    if(not B1Info['isStarted']):
                        continue
                    now = datetime.now()
                    startT = B1Info['startTime']
                    deltaT = now - startT
                    curvesDone = B1Info['curvesDone']
                    curves = B1Info['curves']
                    logger.debug('Curves done = ' + str(curvesDone) + ', curves= ' + str(curves))
                    if(curvesDone):
                        logger.info('{0:d} curves completed @ B1={1:s} out of {2:d} (Elapsed time: {3:s}, avg curve duration: {4:s}s, ETA: {5:s}s).'
                                         .format(B1Info['curvesDone'], B1, B1Info['curves'], str(deltaT),
                                            str(deltaT/curvesDone), str((curves / curvesDone - 1) * deltaT)))
                        lastOuputTime = datetime.now()
                    if(curvesDone == curves):
                        B1Info['Done'] = True
            while((datetime.now() - lastOuputTime).total_seconds() < self.seconds_between_output):
                if( self.end_event.is_set() ):
                    return
                time.sleep(2)


    # ----------------------------------------------------------------------------
    # ----------------------------------------------------------------------------
    def curve_done(self, B1):
        """Informs the timer that a curve has been completed at the given B1"""

        with self.time_table_lck:
            tableEntry = self.time_table[B1]
            assert tableEntry['isStarted']
            tableEntry['curvesDone'] = tableEntry['curvesDone'] + 1


    # ----------------------------------------------------------------------------
    # ----------------------------------------------------------------------------
    def on_work_unit_started(self, work_unit):
        """Informs the timer that the processing of a work unit has started"""

        with self.time_table_lck:
            tableEntry = self.time_table[work_unit.B1]
            if(not tableEntry['isStarted']):
                tableEntry['isStarted'] = True
                tableEntry['startTime'] = datetime.now()

    # ----------------------------------------------------------------------------
    # ----------------------------------------------------------------------------
    def start(self):
        self.thread.start()

    # ----------------------------------------------------------------------------
    # ----------------------------------------------------------------------------
    def end(self):
        self.end_event.set()


# ----------------------------------------------------------------------------
# Create <count> worker threads
# ----------------------------------------------------------------------------
def create_workers(count, work_queue, no_more_work_event, fully_factored_event, timer):
    workers = []
    id = 1
    for i in range(count):
        worker = EcmWorker(work_queue, no_more_work_event, fully_factored_event, id, timer)
        workers.append(worker)
        worker.start()
        id = id + 1
    return workers


# ----------------------------------------------------------------------------
# ----------------------------------------------------------------------------
def create_work_units(args, work_units, fully_factored_event):
    file_index = 0
    for curves_spec in args.curves_spec:
        curves = int(curves_spec[0])
        b1_bound = curves_spec[1]
        ct = int(curves / args.threads)
        rc = curves - args.threads * ct
        worker_c = 0
        while(worker_c < args.threads):
            curvz = ct + (1 if (worker_c < rc) else 0)
            if( not curvz ):
                break
            id = '{0:d}_{1:d}'.format(file_index, worker_c)
            work_unit = EcmWorkUnit(args, curvz, b1_bound, id, fully_factored_event,)
            work_units.append(work_unit)
            worker_c += 1
        file_index += 1

# ----------------------------------------------------------------------------
# ----------------------------------------------------------------------------
def enqueue_work_units(work_queue, work_units, fully_factored_event):
    for work_unit in work_units:
        if( fully_factored_event.is_set()):
            return
        logger.debug('Queueing ' + str(work_unit.curves) + ' curves @ B1=' + work_unit.B1)
        work_queue.put(work_unit)


# ----------------------------------------------------------------------------
# ----------------------------------------------------------------------------
def run_ecm(args):
    work_queue = queue.Queue(args.threads)
    no_more_work_event = threading.Event()
    work_units = []
    with open(args.output_path, 'ab') as output_file:
        fully_factored_event = threading.Event()
        create_work_units(args, work_units, fully_factored_event)
        timer = Timer(work_units, args.delta_progress)
        workers = create_workers(args.threads, work_queue, no_more_work_event, fully_factored_event, timer)
        timer.start()
        # Enqueue the created work units
        enqueue_work_units(work_queue, work_units, fully_factored_event)
        no_more_work_event.set()
        for worker in workers:
            worker.join()
        timer.end()
        if( fully_factored_event.is_set() ):
            logger.info('Number is fully factored!!')            
        for work_unit in work_units:
            if( work_unit.processed ):
                with open(work_unit.output_file_path, 'rb') as worker_output_file:
                    for line in worker_output_file:
                        output_file.write(line)
                os.remove(work_unit.output_file_path)

    results = dict()
    for wk in work_units:
        results[wk.B1] = results[wk.B1] + wk.curves_done() if (wk.B1 in results) else wk.curves_done()
    for b1, c in results.items():
        logger.info('Ran {0:d} curves @ B1={1:s}'.format(c, b1))

    logger.debug('The end.')


# ----------------------------------------------------------------------------
# ----------------------------------------------------------------------------
# Logging set up
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG if (arguments.verbosity >= 1) else logging.INFO)
console_handler.setFormatter(logging.Formatter('| %(asctime)s | %(message)s'))
logger.addHandler(console_handler)

logger.info('')
logger.info('{0:s} version {1:s}'.format(NAME, VERSION))
logger.info('')


# ----------------------------------------------------------------------------
# ----------------------------------------------------------------------------
# main 
run_ecm(arguments)
    
