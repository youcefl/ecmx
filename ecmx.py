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
# ----------------------------------------------------------------------------

import argparse
import threading
import subprocess
import logging
import time
import queue
import os

# ----------------------------------------------------------------------------
# ----------------------------------------------------------------------------
VERSION = '0.3.1'
NAME = 'ecmx'

# ----------------------------------------------------------------------------
# ----------------------------------------------------------------------------
logger = logging.getLogger(NAME)
logger.setLevel(logging.DEBUG)

# ----------------------------------------------------------------------------
# ----------------------------------------------------------------------------
cmd_line_parser = argparse.ArgumentParser()
cmd_line_parser.add_argument( '-v', '--verbosity', action = 'count',
                              default = 0,
                              help = 'Increase verbosity level (use -vv to have ' \
                                    + 'gmp-ecm run in verbose mode.' )
cmd_line_parser.add_argument( '-t', '--threads', required = True, type = int,
                              help = 'Number of threads.' )
cmd_line_parser.add_argument( '-maxmem', '--max_memory',
                              help = 'Maximum memory usage per thread.' )
cmd_line_parser.add_argument( '-k', '--stage2_steps',
                              type = int, required = False,
                              help = 'Number of steps to perform in stage 2.' )
cmd_line_parser.add_argument( '-i', '--input_file', required = True,
                              help = 'Input file.' )
cmd_line_parser.add_argument( '-o', '--output_path', required = True,
                              help = 'Output file path.' )
cmd_line_parser.add_argument( '-e', '--ecm_path', default = 'ecm',
                              help = 'Path of ecm executable.' )
cmd_line_parser.add_argument( '-cs', '--curves_spec', required = True,
                              nargs = 2, help = 'Curves specification as <number of curves> <B1>.',
                              action = 'append',
                              metavar = ('NUMBER_OF_CURVES', 'B1') )
arguments = cmd_line_parser.parse_args()

# ----------------------------------------------------------------------------
# Class holding an ECM work unit i.e. parameters used for running a certain
# number of curves at given B1 bound.
# ----------------------------------------------------------------------------
class EcmWorkUnit:
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

# ----------------------------------------------------------------------------
# Worker thread: gets ECM work unit from the work queue and runs its processing
# ----------------------------------------------------------------------------
class EcmWorker:
    def __init__(self, work_queue, work_finished_event, fully_factored_event):
        self.work_queue = work_queue
        self.work_finished_event = work_finished_event
        self.fully_factored_event = fully_factored_event
        self.thread = threading.Thread( target = self.work, args=() )
    
    def work(self):
        while(True):
            try:
                work_unit = self.work_queue.get_nowait()
                do_run_ecm(work_unit)
            except queue.Empty:
                if(  self.work_finished_event.is_set() 
                  or self.fully_factored_event.is_set() ):
                    break
                time.sleep(1)
                continue

    def start(self):
        self.thread.start()

    def join(self):
        self.thread.join()


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
# Process a work unit
# ----------------------------------------------------------------------------
def do_run_ecm(work_unit):
    # don't bother running a work unit if the number is fully factored
    if( work_unit.fully_factored_event.is_set() ): 
        return
    args = work_unit.args
    cmd = []
    cmd.append(args.ecm_path)
    cmd.append('-timestamp')
    if (args.verbosity >= 2):
        cmd.append('-v')
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
    output_file_path = work_unit.output_file_path
    with open(output_file_path, 'wb') as output_f:
        logger.info('Running {0:d} curves at {1:s}...'.format(work_unit.curves, work_unit.B1))
        proc = subprocess.Popen(cmd, stdout = output_f, stderr = output_f)
        logger.debug('[pid: {0:d}] '.format(proc.pid) + string_array_to_string(cmd)
                         + ' > {0:s} 2>&1'.format(output_file_path))
        while(True):
            if( proc.poll() != None ):
                work_unit.return_code = proc.returncode
                # Bit 3 is set when cofactor is PRP, return code is 8 when
                # the input number itself is found as factor
                if( (work_unit.return_code & 8) and (work_unit.return_code != 8) ):
                    logger.debug('Factor found by [pid:{0:d}], cofactor is PRP.'.format(proc.pid))
                    work_unit.fully_factored_event.set()
                    work_unit.factor_found = True
                elif( work_unit.return_code & 2 ):
                    logger.debug('Factor found by [pid:{0:d}].'.format(proc.pid))
                    work_unit.factor_found = True
                break
            else:
                if( work_unit.fully_factored_event.is_set() ):
                    proc.kill()
                    break
            time.sleep(1)
        logger.debug('Work unit {0:s} processed.'.format(work_unit.id))
        work_unit.processed = True


# ----------------------------------------------------------------------------
# Create <count> worker threads
# ----------------------------------------------------------------------------
def create_workers(count, work_queue, work_finished_event, fully_factored_event):
    workers = []
    for i in range(count):
        worker = EcmWorker(work_queue, work_finished_event, fully_factored_event)
        workers.append(worker)
        worker.start()
    return workers

# ----------------------------------------------------------------------------
# ----------------------------------------------------------------------------
def enqueue_work_units(args, work_queue, work_units, fully_factored_event):
    file_index = 0
    for curves_spec in args.curves_spec:
        curves = int(curves_spec[0])
        b1_bound = curves_spec[1]
        ct = int(curves / args.threads)
        rc = curves - args.threads * ct
        worker_c = 0
        while(worker_c < args.threads):
            curvz = ct + (1 if (worker_c < rc) else 0)
            id = '{0:d}_{1:d}'.format(file_index, worker_c)
            if( fully_factored_event.is_set() ):
                return
            work_unit = EcmWorkUnit(args, curvz, b1_bound, id, fully_factored_event,)
            work_queue.put(work_unit)
            work_units.append(work_unit)
            worker_c += 1
        if( fully_factored_event.is_set() ):
            return
        file_index += 1


# ----------------------------------------------------------------------------
# ----------------------------------------------------------------------------
def run_ecm(args):
    work_queue = queue.Queue(args.threads)
    work_finished_event = threading.Event()
    work_units = []
    with open(args.output_path, 'ab') as output_file:
        fully_factored_event = threading.Event()
        workers = create_workers(args.threads, work_queue, work_finished_event, fully_factored_event)

        enqueue_work_units(args, work_queue, work_units, fully_factored_event)

        work_finished_event.set()
        for worker in workers:
            worker.join()
        if( fully_factored_event.is_set() ):
            logger.info('Number is fully factored!!')            
        for work_unit in work_units:
            if( work_unit.processed ):
                with open(work_unit.output_file_path, 'rb') as worker_output_file:
                    for line in worker_output_file:
                        output_file.write(line)
                os.remove(work_unit.output_file_path)


# ----------------------------------------------------------------------------
# ----------------------------------------------------------------------------

# Set up logging
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG if (arguments.verbosity >= 1) else logging.INFO)
console_handler.setFormatter(logging.Formatter('|-> %(message)s'))
logger.addHandler(console_handler)

logger.info('')
logger.info('{0:s} version {1:s}'.format(NAME, VERSION))
logger.info('')


# ----------------------------------------------------------------------------
# ----------------------------------------------------------------------------
# main 
run_ecm(arguments)
    
