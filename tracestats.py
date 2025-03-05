#!/usr/bin/env python3
'''
@author: Winter Snowfall
@version: 0.4
@date: 28/02/2025
'''

import os
import json
import logging
import argparse
import subprocess
import queue
import threading
import signal

try:
    from traceappnames import TraceAppNames
    TRACEAPPNAMES_IS_IMPORTED = True
except ImportError:
    TRACEAPPNAMES_IS_IMPORTED = False

# logging configuration block
LOGGER_FORMAT = '%(asctime)s %(levelname)s >>> %(message)s'
# logging level for other modules
logging.basicConfig(format=LOGGER_FORMAT, level=logging.ERROR)
logger = logging.getLogger(__name__)
# logging level defaults to INFO
logger.setLevel(logging.INFO) # DEBUG, INFO, WARNING, ERROR, CRITICAL

# constants
TRACE_PARSE_CHUNK_MIN_LINES = 3
# really large trace files can take a long time to process with
# small chuncks, so this is really a fine balance between
# processing times and memory use for buffering
TRACE_PARSE_CHUNK_CALLS = 5000000
TRACE_LOGGING_CHUNK_CALLS = TRACE_PARSE_CHUNK_CALLS * 2
JSON_BASE_KEY = 'tracestats'
JSON_EXPORT_FOLDER_NAME = 'export'
JSON_EXPORT_DEFAULT_FILE_NAME = 'tracestats.json'
# parsing constants
API_ENTRY_CALLS = ('Direct3DCreate8',
                   'Direct3DCreate9Ex',
                   'Direct3DCreate9',
                   'D3D10CreateDevice',
                   'D3D11CreateDevice')
API_ENTRY_CALL_IDENTIFIER = '::'
API_ENTRY_VALUE_DELIMITER = ','
# behavior flags
BEHAVIOR_FLAGS_CALL = '::CreateDevice'
BEHAVIOR_FLAGS_IDENTIFIER = 'BehaviorFlags = '
BEHAVIOR_FLAGS_IDENTIFIER_LENGTH = len(BEHAVIOR_FLAGS_IDENTIFIER)
BEHAVIOR_FLAGS_SPLIT_DELIMITER = '|'
# render states
RENDER_STATES_CALL = '::SetRenderState'
RENDER_STATES_IDENTIFIER = 'State = '
RENDER_STATES_IDENTIFIER_LENGTH = len(RENDER_STATES_IDENTIFIER)
# query types
QUERY_TYPE_CALL_D3D8 = '::GetInfo'
QUERY_TYPE_IDENTIFIER_D3D8 = 'DevInfoID = '
QUERY_TYPE_IDENTIFIER_LENGTH_D3D8 = len(QUERY_TYPE_IDENTIFIER_D3D8)
QUERY_TYPE_CALL_D3D9 = '::CreateQuery'
QUERY_TYPE_IDENTIFIER_D3D9 = 'Type = '
QUERY_TYPE_IDENTIFIER_LENGTH_D3D9 = len(QUERY_TYPE_IDENTIFIER_D3D9)
# formats and pools
API_ENTRY_FORMAT_POOL_BASE_CALL = '::Create'
FORMAT_IDENTIFIER = 'Format = '
FORMAT_IDENTIFIER_LENGTH = len(FORMAT_IDENTIFIER)
POOL_IDENTIFIER = 'Pool = '
POOL_IDENTIFIER_LENGTH = len(POOL_IDENTIFIER)

def sigterm_handler(signum, frame):
    try:
        logger.critical('Halting processing due due to SIGTERM...')
    except:
        pass

    raise SystemExit(0)

def sigint_handler(signum, frame):
    try:
        logger.critical('Halting processing due to SIGINT...')
    except:
        pass

    raise SystemExit(0)

class TraceStats:
    '''Trace parser for statistics generation'''

    # these values aren't usually included in any headers
    @classmethod
    def d3d8_query_type(cls, value):
        try:
            match int(value):
                case 1: return 'D3DDEVINFOID_TEXTUREMANAGER'
                case 2: return 'D3DDEVINFOID_D3DTEXTUREMANAGER'
                case 3: return 'D3DDEVINFOID_TEXTURING'
                case 4: return 'D3DDEVINFOID_VCACHE'
                case 5: return 'D3DDEVINFOID_RESOURCEMANAGER'
                case 6: return 'D3DDEVINFOID_VERTEXSTATS'
                case _: return 'Unknown'
        except ValueError:
            return 'Unknown'

    def __init__(self, trace_input_paths, json_export_path, application_name, apitrace_path, apitrace_threads):
        if trace_input_paths is not None:
            self.trace_input_paths = trace_input_paths[0]
        else:
            self.trace_input_paths = None

        if json_export_path is None:
            if self.trace_input_paths is None or len(self.trace_input_paths) > 1:
                self.json_export_path = os.path.join(JSON_EXPORT_FOLDER_NAME,
                                                     JSON_EXPORT_DEFAULT_FILE_NAME)
            else:
                self.json_export_path = os.path.join(JSON_EXPORT_FOLDER_NAME,
                                                     ''.join((os.path.basename(self.trace_input_paths[0]).split('.')[0], '.json')))
        else:
            self.json_export_path = json_export_path

        if apitrace_path is None:
            try:
                apitrace_find_subprocess = subprocess.run(['which', 'apitrace'],
                                                          stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                                          check=True)
                self.apitrace_path = apitrace_find_subprocess.stdout.decode('utf-8').strip()

            except subprocess.CalledProcessError:
                logger.critical('Unable to find apitrace. Please ensure it is in $PATH or use -a to specify the full path.')
                raise SystemExit(1)
        else:
            if os.path.isfile(apitrace_path):
                self.apitrace_path = apitrace_path
            else:
                logger.critical('Invalid apitrace path specified.')
                raise SystemExit(2)

        try:
            if '.exe' in self.apitrace_path:
                # Use Wine if an .exe file is specified
                self.use_wine_for_apitrace = True
                subprocess_params = ('wine', self.apitrace_path, 'version')
            else:
                self.use_wine_for_apitrace = False
                subprocess_params = (self.apitrace_path, 'version')

            apitrace_check_subprocess = subprocess.run(subprocess_params,
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

        self.application_name = application_name
        self.entry_point = None
        self.api_call_dictionary = {}
        self.behavior_flag_dictionary = {}
        self.render_state_dictionary = {}
        self.query_type_dictionary = {}
        self.format_dictionary = {}
        self.pool_dictionary = {}

        if apitrace_threads is None:
            # default to 1 apitrace thread
            self.thread_count = 1
        else:
            try:
                self.thread_count = int(apitrace_threads)
            except ValueError:
                logger.warning('Invalid number of apitrace threads specified, defaulting to 1')
                self.thread_count = 1

        self.parse_queue = None
        self.process_queue = None
        self.parse_loop = threading.Event()
        self.process_loop = threading.Event()
        self.json_output = {JSON_BASE_KEY: []}

    def process_traces(self):
        for trace_path in self.trace_input_paths:
            if os.path.isfile(trace_path):
                logger.info(f'Processing trace: {trace_path}')

                binary_name = os.path.basename(trace_path).split('.')[0]
                application_name = None
                if self.application_name is not None:
                    application_name = self.application_name
                    logger.info(f'Using application name: {application_name}')
                else:
                    if TRACEAPPNAMES_IS_IMPORTED:
                        application_name = TraceAppNames.get(binary_name)
                        logger.info(f'Application name found in traceappnames repository: {application_name}')

                self.parse_queue = queue.Queue(maxsize=self.thread_count)
                self.parse_loop.set()

                parse_threads = [None] * self.thread_count
                # start trace parsing threads
                for thread_id in range(self.thread_count):
                    parse_threads[thread_id] = threading.Thread(target=self.trace_dump_worker, args=())
                    parse_threads[thread_id].daemon = True
                    parse_threads[thread_id].start()

                self.process_queue = queue.Queue(maxsize=self.thread_count)
                self.process_loop.set()

                # start trace processing thread
                process_thread = threading.Thread(target=self.trace_parse_worker, args=())
                process_thread.daemon = True
                process_thread.start()

                trace_start_call = 0
                trace_end_call = TRACE_PARSE_CHUNK_CALLS

                while self.parse_loop.is_set():
                    try:
                        self.parse_queue.put((trace_start_call, trace_end_call, trace_path),
                                             block=True, timeout=5)

                        trace_start_call = trace_end_call + 1
                        trace_end_call = trace_end_call + TRACE_PARSE_CHUNK_CALLS
                    except queue.Full:
                        logger.debug('Main thread reset while waiting on full queue')
                        pass

                # ensure parsing threads have halted
                for thread_id in range(self.thread_count):
                    parse_threads[thread_id].join()
                # signal the termination of the processing thread
                self.process_loop.clear()
                # ensure the processsing thread has halted
                process_thread.join()

                self.json_output[JSON_BASE_KEY].append({'name': application_name,
                                                        'binary_name': binary_name,
                                                        'api_calls': self.api_call_dictionary,
                                                        'behavior_flags': self.behavior_flag_dictionary,
                                                        'render_states': self.render_state_dictionary,
                                                        'query_types': self.query_type_dictionary,
                                                        'formats': self.format_dictionary,
                                                        'pools': self.pool_dictionary})

                # reset state between processed traces
                self.entry_point = None
                self.api_call_dictionary = {}
                self.behavior_flag_dictionary = {}
                self.render_state_dictionary = {}
                self.query_type_dictionary = {}
                self.format_dictionary = {}
                self.pool_dictionary = {}

                logger.info('Trace processing complete')

            else:
                logger.warning(f'File not found, skipping: {trace_path}')

        json_export = json.dumps(self.json_output, sort_keys=True, indent=4,
                                 separators=(',', ': '), ensure_ascii=False)
        logger.debug(f'JSON export output is: {json_export}')

        with open(self.json_export_path, 'w') as file:
            file.write(json_export)

        logger.info(f'JSON export complete')

    def trace_dump_worker(self):
        # there is no need to drain the queue here, and workers can stop getting
        # new work as soon as one of them has hit an end of trace dump output
        while self.parse_loop.is_set():
            try:
                trace_start_call, trace_end_call, trace_path = self.parse_queue.get(block=True, timeout=5)

                if self.use_wine_for_apitrace:
                    subprocess_params = ('wine', self.apitrace_path, 'dump',
                                        f'--calls={trace_start_call}-{trace_end_call}', trace_path)
                else:
                    subprocess_params = (self.apitrace_path, 'dump',
                                        f'--calls={trace_start_call}-{trace_end_call}', trace_path)

                try:
                    trace_dump_subprocess = subprocess.run(subprocess_params,
                                                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                                            check=True)
                    trace_chunk_lines = trace_dump_subprocess.stdout.decode('utf-8').splitlines()
                    trace_chunk_line_count = len(trace_chunk_lines)

                    if trace_chunk_line_count < TRACE_PARSE_CHUNK_MIN_LINES:
                        if self.parse_loop.is_set():
                            self.parse_loop.clear()
                            logger.info('End of trace dump output detected')

                    else:
                        self.process_queue.put(trace_chunk_lines)
                        # don't hold onto the chunk as it's quite the heavy chonker
                        trace_chunk_lines = None

                except subprocess.CalledProcessError:
                    logger.critical('Critical exception during the apitrace dump process')
                    self.parse_loop.clear()

            except queue.Empty:
                logger.debug('Parsing thread reset while waiting on empty queue')
                pass

    def trace_parse_worker(self):
        while self.process_loop.is_set() or not self.process_queue.empty():
            try:
                trace_chunk_lines = self.process_queue.get(block=True, timeout=5)

                trace_call_count_max = 0

                for trace_line in trace_chunk_lines:
                    # there are, surprisingly, quite a lot of
                    # blank/padding lines in an apitrace dump
                    if len(trace_line) == 0:
                        continue
                    # also early skip embedded comments
                    elif trace_line.startswith('//'):
                        continue

                    # typically, the API entrypoint can be found
                    # on the fist line of an apitrace
                    if self.entry_point is None :
                        for ordinal in range(len(API_ENTRY_CALLS)):
                            if API_ENTRY_CALLS[ordinal] in trace_line:
                                self.entry_point = API_ENTRY_CALLS[ordinal]
                                # add the entrypoint to the call dictionary
                                existing_value = self.api_call_dictionary.get(API_ENTRY_CALLS[ordinal], 0)
                                self.api_call_dictionary[API_ENTRY_CALLS[ordinal]] = existing_value + 1
                                # otherwise D3D9 will get added to D3D9Ex, heh
                                break

                    # TODO: we may want to include other identifiers here as well,
                    # especially for other base entry calls, should apitrace support them
                    if API_ENTRY_CALL_IDENTIFIER in trace_line:
                        split_line = trace_line.split()

                        # '::' can also be part of shader comments at times,
                        # in which case the cast bellow will raise a ValueError
                        try:
                            trace_call_count_max = int(split_line[0])
                            logger.debug(f'Found call count: {trace_call_count_max}')
                            # parse API calls
                            call = split_line[1].split('(')[0]
                            logger.debug(f'Found call: {call}')

                            existing_value = self.api_call_dictionary.get(call, 0)
                            self.api_call_dictionary[call] = existing_value + 1

                            # parse device behavior flags, render states, format
                            # and pool values for D3D8, D3D9Ex, and D3D9 apitraces
                            if (self.entry_point == API_ENTRY_CALLS[0] or
                                self.entry_point == API_ENTRY_CALLS[1] or
                                self.entry_point == API_ENTRY_CALLS[2]):
                                if BEHAVIOR_FLAGS_CALL in call:
                                    logger.debug(f'Found behavior flags on line: {trace_line}')

                                    behavior_flags_start = trace_line.find(BEHAVIOR_FLAGS_IDENTIFIER) + BEHAVIOR_FLAGS_IDENTIFIER_LENGTH
                                    behavior_flags = trace_line[behavior_flags_start:trace_line.find(API_ENTRY_VALUE_DELIMITER,
                                                                                                    behavior_flags_start)].strip()
                                    behavior_flags = behavior_flags.split(BEHAVIOR_FLAGS_SPLIT_DELIMITER)

                                    for behavior_flag in behavior_flags:
                                        behavior_flag_stripped = behavior_flag.strip()
                                        existing_value = self.behavior_flag_dictionary.get(behavior_flag_stripped, 0)
                                        self.behavior_flag_dictionary[behavior_flag_stripped] = existing_value + 1

                                elif RENDER_STATES_CALL in call:
                                    logger.debug(f'Found render states on line: {trace_line}')

                                    render_state_start = trace_line.find(RENDER_STATES_IDENTIFIER) + RENDER_STATES_IDENTIFIER_LENGTH
                                    render_state = trace_line[render_state_start:trace_line.find(API_ENTRY_VALUE_DELIMITER,
                                                                                                render_state_start)].strip()

                                    existing_value = self.render_state_dictionary.get(render_state, 0)
                                    self.render_state_dictionary[render_state] = existing_value + 1
                                    continue

                                # D3D8 uses IDirect3DDevice8::GetInfo calls to initiate queries
                                elif self.entry_point == API_ENTRY_CALLS[0] and QUERY_TYPE_CALL_D3D8 in call:
                                    logger.debug(f'Found query type on line: {trace_line}')

                                    query_type_start = trace_line.find(QUERY_TYPE_IDENTIFIER_D3D8) + QUERY_TYPE_IDENTIFIER_LENGTH_D3D8
                                    query_type = trace_line[query_type_start:trace_line.find(API_ENTRY_VALUE_DELIMITER,
                                                                                             query_type_start)].strip()
                                    query_type_decoded = self.d3d8_query_type(query_type)
                                    logger.debug(f'Decoded query type is: {query_type_decoded}')

                                    existing_value = self.query_type_dictionary.get(query_type_decoded, 0)
                                    self.query_type_dictionary[query_type_decoded] = existing_value + 1
                                    continue

                                # D3D9Ex/D3D9 use IDirect3DQuery9::CreateQuery to initiate queries
                                elif (self.entry_point == API_ENTRY_CALLS[1] or
                                      self.entry_point == API_ENTRY_CALLS[2]) and QUERY_TYPE_CALL_D3D9 in call:
                                    logger.debug(f'Found query type on line: {trace_line}')

                                    query_type_start = trace_line.find(QUERY_TYPE_IDENTIFIER_D3D9) + QUERY_TYPE_IDENTIFIER_LENGTH_D3D9
                                    query_type = trace_line[query_type_start:trace_line.find(API_ENTRY_VALUE_DELIMITER,
                                                                                             query_type_start)].strip()

                                    existing_value = self.query_type_dictionary.get(query_type, 0)
                                    self.query_type_dictionary[query_type] = existing_value + 1
                                    continue

                                if API_ENTRY_FORMAT_POOL_BASE_CALL in call:
                                    if FORMAT_IDENTIFIER in trace_line:
                                        logger.debug(f'Found format on line: {trace_line}')

                                        format_start = trace_line.find(FORMAT_IDENTIFIER) + FORMAT_IDENTIFIER_LENGTH
                                        format_value = trace_line[format_start:trace_line.find(API_ENTRY_VALUE_DELIMITER,
                                                                                            format_start)].strip()

                                        existing_value = self.format_dictionary.get(format_value, 0)
                                        self.format_dictionary[format_value] = existing_value + 1

                                    if POOL_IDENTIFIER in trace_line:
                                        logger.debug(f'Found pool on line: {trace_line}')

                                        pool_start = trace_line.find(POOL_IDENTIFIER) + POOL_IDENTIFIER_LENGTH
                                        pool_value = trace_line[pool_start:trace_line.find(API_ENTRY_VALUE_DELIMITER,
                                                                                        pool_start)].strip()

                                        existing_value = self.pool_dictionary.get(pool_value, 0)
                                        self.pool_dictionary[pool_value] = existing_value + 1

                        except ValueError:
                            pass

                    else:
                        logger.debug(f'Skipped parsing of line: {trace_line}')

                if trace_call_count_max > 0 and trace_call_count_max % TRACE_LOGGING_CHUNK_CALLS == 0:
                    logger.info(f'Proccessed {trace_call_count_max} apitrace calls...')

                # don't hold onto the chunk as it's quite the heavy chonker
                trace_chunk_lines = None

            except queue.Empty:
                logger.debug('Processsing thread reset while waiting on empty queue')
                pass

    def join_json(self):
        trace_file_paths = []

        for filename in os.listdir(JSON_EXPORT_FOLDER_NAME):
            if filename.endswith('.json'):
                trace_file_paths.append(os.path.join(JSON_EXPORT_FOLDER_NAME, filename))

        trace_file_paths.sort()

        for trace_file_path in trace_file_paths:
            try:
                logger.info(f'Processing {os.path.basename(trace_file_path)} for joining...')

                with open(trace_file_path, 'r') as file:
                    file_content = file.read()

                single_trace_content_items = json.loads(file_content).get(JSON_BASE_KEY)

                for item in single_trace_content_items:
                    self.json_output[JSON_BASE_KEY].append(item)

            except json.JSONDecodeError:
                logger.critical(f'Unable to parse JSON file: {trace_file_path}')
                raise SystemExit(5)

        joined_json_export = json.dumps(self.json_output, sort_keys=True, indent=4,
                                        separators=(',', ': '), ensure_ascii=False)
        logger.debug(f'Joined JSON export output is: {joined_json_export}')

        with open(self.json_export_path, 'w') as file:
            file.write(joined_json_export)

        logger.info(f'Joined JSON export complete')

if __name__ == "__main__":
    # catch SIGTERM and exit gracefully
    signal.signal(signal.SIGTERM, sigterm_handler)
    # catch SIGINT and exit gracefully
    signal.signal(signal.SIGINT, sigint_handler)

    parser = argparse.ArgumentParser(description=('tracestats - generate API call statistics from apitraces'), add_help=False)

    required = parser.add_argument_group('required arguments')
    group = required.add_mutually_exclusive_group(required=True)
    optional = parser.add_argument_group('optional arguments')

    group.add_argument('-i', '--input', help='paths of apitrace files to process', nargs='*', action='append')
    group.add_argument('-j', '--join', help=f'joins all traces in the {JSON_EXPORT_FOLDER_NAME} directory '
                                            f'into a single {JSON_EXPORT_DEFAULT_FILE_NAME} file', action='store_true')

    optional.add_argument('-h', '--help', action='help', help='show this help message and exit')
    optional.add_argument('-t', '--threads', help='number of apitrace dump threads to spawn')
    optional.add_argument('-o', '--output', help='path and filename of the JSON export')
    optional.add_argument('-n', '--name', help='specify a name for the apitraced application, using double quotes')
    optional.add_argument('-a', '--apitrace', help='path to the apitrace executable')

    args = parser.parse_args()

    tracestats = TraceStats(args.input, args.output, args.name, args.apitrace, args.threads)
    if not args.join:
        tracestats.process_traces()
    else:
        tracestats.join_json()

