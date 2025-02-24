#!/usr/bin/env python3
'''
@author: Winter Snowfall
@version: 0.1
@date: 24/02/2025
'''

import os
import json
import logging
import argparse
import subprocess

# logging configuration block
LOGGER_FORMAT = '%(asctime)s %(levelname)s >>> %(message)s'
# logging level for other modules
logging.basicConfig(format=LOGGER_FORMAT, level=logging.ERROR)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# constants
TRACE_PARSE_CHUNK_MIN_LINES = 3
TRACE_PARSE_CHUNK_LINES = 500000
TRACE_LOGGING_CHUNK_LINES = TRACE_PARSE_CHUNK_LINES * 2
API_ENTRY_CALLS = ('Direct3DCreate8', 'Direct3DCreate9', 'D3D10CreateDevice', 'D3D11CreateDevice')

class TraceStatsWorker:
    '''Trace parser worker'''

    def __init__(self, traces_paths, json_export_path, apitrace_path):
        self.traces_paths = traces_paths[0]

        if json_export_path is None:
            self.json_export_path = 'tracestats.json'
        else:
            self.json_export_path = json_export_path

        if apitrace_path is None:
            try:
                apitrace_find_subprocess = subprocess.run(['which', 'apitrace'],
                                                        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                                        check=True)
                self.apitrace_path = apitrace_check_subprocess.stdout.decode('utf-8').split()
            
            except subprocess.CalledProcessError:
                logger.critical('Unable to find apitrace. Please ensure it is in $PATH or use -a to specify the full path.')
                raise SystemExit(1)
        else:
            if os.path.isfile(apitrace_path):
                if '.exe' in apitrace_path:
                    self.apitrace_path = ('wine', apitrace_path)
                else:
                    self.apitrace_path = apitrace_path
            else:
                logger.critical('Invalid apitrace path specified.')
                raise SystemExit(2)

        try:
            apitrace_check_subprocess = subprocess.run([*self.apitrace_path, 'version'],
                                                        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                                        check=True)
            apitrace_check_output = apitrace_check_subprocess.stdout.decode('utf-8').split()

            try:
                if apitrace_check_output[0] != 'apitrace' and float(apitrace_check_output[1]) < 12.0:
                    logger.critical('Invalid apitrace version. Please use at least apitrace 12.0.')
                    raise SystemExit(3)
            except ValueError:
                logger.critical('Invalid apitrace executable')
                raise SystemExit(4)

        except subprocess.CalledProcessError:
            logger.critical('Invalid apitrace executable')
            raise SystemExit(5)

        self.calls_dictionary = {}
        self.trace_max_call = 0
        self.trace_start_call = 0
        self.trace_end_call = TRACE_PARSE_CHUNK_LINES
        self.trace_chunk = ''
        self.trace_chunk_line_count = 0
        self.api_name = None
        self.json_output = {"TraceStats": []}

    def trace_dump(self):
        for trace_path in self.traces_paths:
            if os.path.isfile(trace_path):
                logger.info(f'Processing trace: {trace_path}')

                while self.trace_chunk_line_count >= TRACE_PARSE_CHUNK_MIN_LINES or self.trace_start_call == 0:
                    try:
                        trace_dump_subprocess = subprocess.run([*self.apitrace_path, 'dump', f'--calls={self.trace_start_call}-{self.trace_end_call}', trace_path],
                                                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                                                check=True)
                        self.trace_chunk = trace_dump_subprocess.stdout.decode('utf-8')

                    except subprocess.CalledProcessError:
                        logger.critical('Critical exception during the apitrace dump process')
                        raise SystemExit(6)

                    #logger.info(f'Chunk: {self.trace_chunk}')
                    self.trace_chunk_line_count = self.trace_call_count()

                    if self.trace_max_call % TRACE_LOGGING_CHUNK_LINES == 0:
                        logger.info(f'Proccessed {self.trace_end_call} calls...')

                    self.trace_start_call = self.trace_end_call + 1
                    self.trace_end_call = self.trace_end_call + TRACE_PARSE_CHUNK_LINES

                self.json_output["TraceStats"].append({'Trace_Name': os.path.basename(trace_path).split('.')[0],
                                                       'API': self.api_name,
                                                       'Call_Total': self.trace_max_call,
                                                       'Call_Stats': self.calls_dictionary})

                output_items = []
                for key, value in dict(sorted(self.calls_dictionary.items())).items():
                    output_items.append(f'{key}: {value}')
                logger.debug(''.join(('Found and exported the following call stats:\n   ', '\n   '.join((output_items)))))

                # reset state between processed traces
                self.calls_dictionary = {}
                self.trace_max_call = 0
                self.trace_start_call = 0
                self.trace_end_call = TRACE_PARSE_CHUNK_LINES
                self.trace_chunk = ''
                self.trace_chunk_line_count = 0
                self.api_name = None

                logger.info('Trace processing complete')
            
            else:
                logger.warning(f'File not found, skipping: {trace_path}')

        json_export = json.dumps(self.json_output, sort_keys=True, indent=4,
                                 separators=(',', ': '), ensure_ascii=False)

        with open(self.json_export_path, 'w') as file:
            file.write(json_export)

        logger.info(f'JSON export complete')

    def trace_call_count(self):
        trace_line_count = 0

        for trace_line in self.trace_chunk.splitlines():
            if self.api_name == None:
                if API_ENTRY_CALLS[0] in trace_line:
                    self.api_name = 'D3D8'
                elif API_ENTRY_CALLS[1] in trace_line:
                    self.api_name = 'D3D9'
                elif API_ENTRY_CALLS[2] in trace_line:
                    self.api_name = 'D3D10'
                elif API_ENTRY_CALLS[3] in trace_line:
                    self.api_name = 'D3D11'

            if '::' in trace_line:
                split_line = trace_line.split()

                # '::' can also be part of shader comments at times,
                # in which case the cast bellow will raise a ValueError
                try:
                    self.trace_max_call = int(split_line[0])
                    logger.debug(f'Max call no: {self.trace_max_call}')
                    call = split_line[1].split('(')[0]
                    logger.debug(f'Found call: {call}')

                    existing_value = self.calls_dictionary.get(call, None)
                    if existing_value is None:
                        self.calls_dictionary[call] = 1
                    else:
                        self.calls_dictionary[call] = existing_value + 1
                
                except ValueError:
                    pass
            
            trace_line_count = trace_line_count + 1

        return trace_line_count

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=('tracestats - generate API call statistics from apitraces'), add_help=False)

    required = parser.add_argument_group('required arguments')
    optional = parser.add_argument_group('optional arguments')

    required.add_argument('-t', '--traces', help='paths of apitrace files to process', nargs='*', action='append', required=True)

    optional.add_argument('-h', '--help', action='help', help='show this help message and exit')
    optional.add_argument('-o', '--output', help='path and files of the JSON export')
    optional.add_argument('-a', '--apitrace', help='path to the apitrace executable')

    args = parser.parse_args()

    trace_worker = TraceStatsWorker(args.traces, args.output, args.apitrace)
    trace_worker.trace_dump()

