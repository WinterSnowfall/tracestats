#!/usr/bin/env python3
'''
@author: Winter Snowfall
@version: 0.6
@date: 12/03/2025
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
API_ENTRY_CALLS = {'Direct3DCreate8': 'D3D8',
                   'Direct3DCreate9Ex': 'D3D9Ex', # ensure D3D9Ex gets checked before D3D9
                   'Direct3DCreate9': 'D3D9',
                   'D3D10CreateDeviceAndSwapChain1': 'D3D10',
                   'D3D10CreateDevice1': 'D3D10',
                   'D3D10CreateDeviceAndSwapChain': 'D3D10',
                   'D3D10CreateDevice': 'D3D10',
                   'D3D10CoreCreateDevice': 'D3D10',
                   'D3D11CreateDeviceAndSwapChain': 'D3D11',
                   'D3D11CreateDevice': 'D3D11',
                   'D3D11CoreCreateDevice': 'D3D11'}
API_BASE_CALLS = {**API_ENTRY_CALLS, 'CreateDXGIFactory': 'DXGI',
                                     'CreateDXGIFactory1': 'DXGI',
                                     'CreateDXGIFactory2': 'DGXI'}
API_ENTRY_CALL_IDENTIFIER = '::'
API_ENTRY_VALUE_DELIMITER = ','

############################## D3D8, D3D9Ex, D3D9 ##############################
# behavior flags
BEHAVIOR_AND_PRESENT_PARAMETERS_FLAGS_CALL = '::CreateDevice'
BEHAVIOR_FLAGS_IDENTIFIER = 'BehaviorFlags = '
BEHAVIOR_FLAGS_IDENTIFIER_LENGTH = len(BEHAVIOR_FLAGS_IDENTIFIER)
BEHAVIOR_FLAGS_SPLIT_DELIMITER = '|'
# present parameters
PRESENT_PARAMETERS_IDENTIFIER = 'pPresentationParameters = &{'
PRESENT_PARAMETERS_SKIP_IDENTIFIER = 'pPresentationParameters = ?'
PRESENT_PARAMETERS_IDENTIFIER_LENGTH = len(PRESENT_PARAMETERS_IDENTIFIER)
PRESENT_PARAMETERS_IDENTIFIER_END = '}'
PRESENT_PARAMETERS_SPLIT_DELIMITER = ','
PRESENT_PARAMETERS_SKIPPED = ('BackBufferWidth', 'BackBufferHeight', 'hDeviceWindow', 'Windowed', 'FullScreen_RefreshRateInHz')
PRESENT_PARAMETERS_VALUE_SPLIT_DELIMITER = ' = '
# render states
RENDER_STATES_CALL = '::SetRenderState'
RENDER_STATES_IDENTIFIER = 'State = '
RENDER_STATES_IDENTIFIER_LENGTH = len(RENDER_STATES_IDENTIFIER)
# query types
QUERY_TYPE_CALL_D3D8 = '::GetInfo'
QUERY_TYPE_IDENTIFIER_D3D8 = 'DevInfoID = '
QUERY_TYPE_IDENTIFIER_LENGTH_D3D8 = len(QUERY_TYPE_IDENTIFIER_D3D8)
QUERY_TYPE_CALL_D3D9_10_11 = '::CreateQuery'
QUERY_TYPE_IDENTIFIER_D3D9 = 'Type = '
QUERY_TYPE_IDENTIFIER_LENGTH_D3D9 = len(QUERY_TYPE_IDENTIFIER_D3D9)
QUERY_TYPE_IDENTIFIER_D3D10_11 = 'Query = '
QUERY_TYPE_IDENTIFIER_D3D10_11_LENGTH = len(QUERY_TYPE_IDENTIFIER_D3D10_11)
# formats
API_ENTRY_FORMAT_BASE_CALL = '::Create'
FORMAT_IDENTIFIER = 'Format = '
FORMAT_IDENTIFIER_LENGTH = len(FORMAT_IDENTIFIER)
# pools
POOL_IDENTIFIER = 'Pool = '
POOL_IDENTIFIER_LENGTH = len(POOL_IDENTIFIER)
############################## D3D8, D3D9Ex, D3D9 ##############################

################################# D3D10, D3D11 #################################
# device flags (treat these as d3d9 behavior flags for simplicity)
DEVICE_FLAGS_AND_FEATURE_LEVELS_CALL = 'CreateDevice'
DEVICE_FLAGS_IDENTIFIER = 'Flags = '
DEVICE_FLAGS_IDENTIFIER_LENGTH = len(DEVICE_FLAGS_IDENTIFIER)
DEVICE_FLAGS_SKIP_IDENTIFIER = 'Flags = 0x0'
DEVICE_FLAGS_SPLIT_DELIMITER = '|'
# feature levels
FEATURE_LEVELS_IDENTIFIER = 'pFeatureLevels = {'
FEATURE_LEVELS_IDENTIFIER_LENGTH = len(FEATURE_LEVELS_IDENTIFIER)
FEATURE_LEVELS_IDENTIFIER_ONE = 'pFeatureLevels = &'
FEATURE_LEVELS_IDENTIFIER_ONE_LENGTH = len(FEATURE_LEVELS_IDENTIFIER_ONE)
FEATURE_LEVELS_SKIP_IDENTIFIER = 'pFeatureLevels = NULL'
FEATURE_LEVELS_IDENTIFIER_END = '}'
# rastizer state
RASTIZER_STATE_CALL = '::CreateRasterizerState'
RASTIZER_STATE_IDENTIFIER = 'pRasterizerDesc = &{'
RASTIZER_STATE_IDENTIFIER_LENGTH = len(RASTIZER_STATE_IDENTIFIER)
RASTIZER_STATE_IDENTIFIER_END = '}'
# blend state
BLEND_STATE_CALL = '::CreateBlendState'
BLEND_STATE_IDENTIFIER = 'pBlendStateDesc = &{'
BLEND_STATE_IDENTIFIER_LENGTH = len(RASTIZER_STATE_IDENTIFIER)
BLEND_STATE_IDENTIFIER_END_D3D10 = ', BlendEnable = '
BLEND_STATE_IDENTIFIER_END_D3D11 = ', RenderTarget = '
# usage
USAGE_IDENTIFIER = 'Usage = '
USAGE_IDENTIFIER_LENGTH = len(USAGE_IDENTIFIER)
USAGE_IDENTIFIER_SKIP = 'DXGI_USAGE_'
# bind flags
BIND_FLAGS_IDENTIFIER = 'BindFlags = '
BIND_FLAGS_IDENTIFIER_LENGTH = len(BIND_FLAGS_IDENTIFIER)
BIND_FLAGS_SKIP_IDENTIFIER = 'BindFlags = 0x0'
BIND_FLAGS_SPLIT_DELIMITER = '|'
################################# D3D10, D3D11 #################################

DEFERRED_CONTEXT_CALL = '::CreateDeferredContext'

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
                                                     ''.join((os.path.basename(self.trace_input_paths[0]).rsplit('.', 1)[0], '.json')))
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
        self.api = None
        self.api_call_dictionary = {}
        self.behavior_flag_dictionary = {}
        self.present_parameter_dictionary = {}
        self.render_state_dictionary = {}
        self.query_type_dictionary = {}
        self.format_dictionary = {}
        self.pool_dictionary = {}
        self.device_flag_dictionary = {}
        self.feature_level_dictionary = {}
        self.rastizer_state_dictionary = {}
        self.blend_state_dictionary = {}
        self.usage_dictionary = {}
        self.bind_flag_dictionary = {}

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

                binary_name_raw = binary_name = os.path.basename(trace_path).rsplit('.', 1)[0]
                # workaround for renamed generic game/Game.exe apitraces
                if binary_name_raw.upper().startswith('GAME'):
                    binary_name = binary_name_raw[:4]
                elif binary_name_raw.endswith('_'):
                    binary_name = binary_name_raw[:-1]
                application_name = None
                if self.application_name is not None:
                    application_name = self.application_name
                    logger.info(f'Using application name: {application_name}')
                elif TRACEAPPNAMES_IS_IMPORTED:
                    application_name = TraceAppNames.get(binary_name_raw)
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

                return_dictionary = {}
                return_dictionary['name'] = application_name
                return_dictionary['binary_name'] = binary_name
                if len(self.api_call_dictionary) > 0:
                    return_dictionary['api_calls'] = self.api_call_dictionary
                if len(self.present_parameter_dictionary) > 0:
                    return_dictionary['present_parameters'] = self.present_parameter_dictionary
                if len(self.behavior_flag_dictionary) > 0:
                    return_dictionary['behavior_flags'] = self.behavior_flag_dictionary
                if len(self.render_state_dictionary) > 0:
                    return_dictionary['render_states'] = self.render_state_dictionary
                if len(self.query_type_dictionary) > 0:
                    return_dictionary['query_types'] = self.query_type_dictionary
                if len(self.format_dictionary) > 0:
                    return_dictionary['formats'] = self.format_dictionary
                if len(self.pool_dictionary) > 0:
                    return_dictionary['pools'] = self.pool_dictionary
                if len(self.device_flag_dictionary) > 0:
                    return_dictionary['device_flags'] = self.device_flag_dictionary
                if len(self.feature_level_dictionary) > 0:
                    return_dictionary['feature_levels'] = self.feature_level_dictionary
                if len(self.rastizer_state_dictionary) > 0:
                    return_dictionary['rastizer_states'] = self.rastizer_state_dictionary
                if len(self.blend_state_dictionary) > 0:
                    return_dictionary['blend_states'] = self.blend_state_dictionary
                if len(self.usage_dictionary) > 0:
                    return_dictionary['usage'] = self.usage_dictionary
                if len(self.bind_flag_dictionary) > 0:
                    return_dictionary['bind_flags'] = self.bind_flag_dictionary

                self.json_output[JSON_BASE_KEY].append(return_dictionary)

                # reset state between processed traces
                self.api = None
                self.api_call_dictionary = {}
                self.behavior_flag_dictionary = {}
                self.present_parameter_dictionary = {}
                self.render_state_dictionary = {}
                self.query_type_dictionary = {}
                self.format_dictionary = {}
                self.pool_dictionary = {}
                self.device_flag_dictionary = {}
                self.feature_level_dictionary = {}
                self.rastizer_state_dictionary = {}
                self.blend_state_dictionary = {}
                self.usage_dictionary = {}
                self.bind_flag_dictionary = {}

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
                trace_call_counter = 0
                trace_call_counter_notification = 0
                trace_deffered_context_warned = False

                for trace_line in trace_chunk_lines:
                    # there are, surprisingly, quite a lot of
                    # blank/padding lines in an apitrace dump
                    if len(trace_line) == 0:
                        continue
                    # also early skip embedded comments
                    elif trace_line.startswith('//'):
                        continue
                    # early skip whitespaced lines (not API calls)
                    elif trace_line.startswith('  '):
                        continue

                    split_line = trace_line.split()

                    # otherwise unnumbered lines will raise a ValueError
                    try:
                        trace_call_counter = int(split_line[0])
                        logger.debug(f'Found call count: {trace_call_counter}')
                    except ValueError:
                        pass

                    if (API_ENTRY_CALL_IDENTIFIER in trace_line or
                        any(api_base_call in trace_line for api_base_call in API_BASE_CALLS.keys())):
                        # typically, the API entrypoint can be found
                        # on the fist line of an apitrace
                        if self.api is None :
                            for key, value in API_ENTRY_CALLS.items():
                                if key in split_line[1]:
                                    self.api = value
                                    logger.info(f'Detected API: {self.api}')
                                    # otherwise D3D9 will get added to D3D9Ex, heh
                                    break

                        # parse API calls
                        call = split_line[1].split('(')[0]
                        logger.debug(f'Found call: {call}')

                        existing_value = self.api_call_dictionary.get(call, 0)
                        self.api_call_dictionary[call] = existing_value + 1

                        # parse device behavior flags, render states, format
                        # and pool values for D3D8, D3D9Ex, and D3D9 apitraces
                        if self.api == 'D3D8' or self.api == 'D3D9Ex' or self.api == 'D3D9':
                            if BEHAVIOR_AND_PRESENT_PARAMETERS_FLAGS_CALL in call:
                                logger.debug(f'Found behavior flags and present parameters on line: {trace_line}')

                                behavior_flags_start = trace_line.find(BEHAVIOR_FLAGS_IDENTIFIER) + BEHAVIOR_FLAGS_IDENTIFIER_LENGTH
                                behavior_flags = trace_line[behavior_flags_start:trace_line.find(API_ENTRY_VALUE_DELIMITER,
                                                                                                behavior_flags_start)].strip()
                                behavior_flags = behavior_flags.split(BEHAVIOR_FLAGS_SPLIT_DELIMITER)

                                for behavior_flag in behavior_flags:
                                    behavior_flag_stripped = behavior_flag.strip()
                                    existing_value = self.behavior_flag_dictionary.get(behavior_flag_stripped, 0)
                                    self.behavior_flag_dictionary[behavior_flag_stripped] = existing_value + 1

                                if PRESENT_PARAMETERS_SKIP_IDENTIFIER not in trace_line:
                                    present_parameters_start = trace_line.find(PRESENT_PARAMETERS_IDENTIFIER) + PRESENT_PARAMETERS_IDENTIFIER_LENGTH
                                    present_parameters = trace_line[present_parameters_start:trace_line.find(PRESENT_PARAMETERS_IDENTIFIER_END,
                                                                                                    present_parameters_start)].strip()
                                    present_parameters = present_parameters.split(PRESENT_PARAMETERS_SPLIT_DELIMITER)

                                    for present_parameter in present_parameters:
                                        present_parameter_stripped = present_parameter.strip()
                                        present_parameter_key, present_parameter_value = present_parameter_stripped.split(PRESENT_PARAMETERS_VALUE_SPLIT_DELIMITER)
                                        if present_parameter_key not in PRESENT_PARAMETERS_SKIPPED:
                                            if present_parameter_key != 'Flags' or present_parameter_value != '0x0':
                                                existing_value = self.present_parameter_dictionary.get(present_parameter_stripped, 0)
                                                self.present_parameter_dictionary[present_parameter_stripped] = existing_value + 1

                            elif RENDER_STATES_CALL in call:
                                logger.debug(f'Found render states on line: {trace_line}')

                                render_state_start = trace_line.find(RENDER_STATES_IDENTIFIER) + RENDER_STATES_IDENTIFIER_LENGTH
                                render_state = trace_line[render_state_start:trace_line.find(API_ENTRY_VALUE_DELIMITER,
                                                                                            render_state_start)].strip()

                                existing_value = self.render_state_dictionary.get(render_state, 0)
                                self.render_state_dictionary[render_state] = existing_value + 1
                                continue

                            # D3D8 uses IDirect3DDevice8::GetInfo calls to initiate queries
                            elif self.api == 'D3D8' and QUERY_TYPE_CALL_D3D8 in call:
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
                            elif (self.api == 'D3D9Ex' or self.api == 'D3D9') and QUERY_TYPE_CALL_D3D9_10_11 in call:
                                logger.debug(f'Found query type on line: {trace_line}')

                                query_type_start = trace_line.find(QUERY_TYPE_IDENTIFIER_D3D9) + QUERY_TYPE_IDENTIFIER_LENGTH_D3D9
                                query_type = trace_line[query_type_start:trace_line.find(API_ENTRY_VALUE_DELIMITER,
                                                                                            query_type_start)].strip()

                                existing_value = self.query_type_dictionary.get(query_type, 0)
                                self.query_type_dictionary[query_type] = existing_value + 1
                                continue

                            elif API_ENTRY_FORMAT_BASE_CALL in call:
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

                        elif self.api == 'D3D10' or self.api == 'D3D11':
                            if DEVICE_FLAGS_AND_FEATURE_LEVELS_CALL in call:
                                logger.debug(f'Found device flags and feature levels on line: {trace_line}')

                                if DEVICE_FLAGS_SKIP_IDENTIFIER not in trace_line:
                                    device_flags_start = trace_line.find(DEVICE_FLAGS_IDENTIFIER) + DEVICE_FLAGS_IDENTIFIER_LENGTH
                                    device_flags = trace_line[device_flags_start:trace_line.find(API_ENTRY_VALUE_DELIMITER,
                                                                                                device_flags_start)].strip()
                                    device_flags = device_flags.split(DEVICE_FLAGS_SPLIT_DELIMITER)

                                    for device_flag in device_flags:
                                        device_flag_stripped = device_flag.strip()
                                        existing_value = self.device_flag_dictionary.get(device_flag_stripped, 0)
                                        self.device_flag_dictionary[device_flag_stripped] = existing_value + 1

                                if FEATURE_LEVELS_SKIP_IDENTIFIER not in trace_line:
                                    if FEATURE_LEVELS_IDENTIFIER in trace_line:
                                        feature_levels_start = trace_line.find(FEATURE_LEVELS_IDENTIFIER) + FEATURE_LEVELS_IDENTIFIER_LENGTH
                                        feature_levels = trace_line[feature_levels_start:trace_line.find(FEATURE_LEVELS_IDENTIFIER_END,
                                                                                                        feature_levels_start)].strip()
                                        feature_levels = feature_levels.split(API_ENTRY_VALUE_DELIMITER)

                                        for feature_level in feature_levels:
                                            feature_level_stripped = feature_level.strip()
                                            existing_value = self.feature_level_dictionary.get(feature_level_stripped, 0)
                                            self.feature_level_dictionary[feature_level_stripped] = existing_value + 1

                                    elif FEATURE_LEVELS_IDENTIFIER_ONE in trace_line:
                                        feature_levels_start = trace_line.find(FEATURE_LEVELS_IDENTIFIER_ONE) + FEATURE_LEVELS_IDENTIFIER_ONE_LENGTH
                                        feature_level_stripped = trace_line[feature_levels_start:trace_line.find(API_ENTRY_VALUE_DELIMITER,
                                                                                                                    feature_levels_start)].strip()
                                        existing_value = self.feature_level_dictionary.get(feature_level_stripped, 0)
                                        self.feature_level_dictionary[feature_level_stripped] = existing_value + 1

                            elif QUERY_TYPE_CALL_D3D9_10_11 in call:
                                logger.debug(f'Found query type on line: {trace_line}')

                                query_type_start = trace_line.find(QUERY_TYPE_IDENTIFIER_D3D10_11) + QUERY_TYPE_IDENTIFIER_D3D10_11_LENGTH
                                query_type = trace_line[query_type_start:trace_line.find(API_ENTRY_VALUE_DELIMITER,
                                                                                         query_type_start)].strip()

                                existing_value = self.query_type_dictionary.get(query_type, 0)
                                self.query_type_dictionary[query_type] = existing_value + 1
                                continue

                            elif RASTIZER_STATE_CALL in call:
                                logger.debug(f'Found rastizer state on line: {trace_line}')

                                if RASTIZER_STATE_IDENTIFIER in trace_line:
                                    rastizer_states_start = trace_line.find(RASTIZER_STATE_IDENTIFIER) + RASTIZER_STATE_IDENTIFIER_LENGTH
                                    rastizer_states = trace_line[rastizer_states_start:trace_line.find(RASTIZER_STATE_IDENTIFIER_END,
                                                                                                        rastizer_states_start)].strip()
                                    rastizer_states = rastizer_states.split(API_ENTRY_VALUE_DELIMITER)

                                    for rastizer_state in rastizer_states:
                                        rastizer_state_stripped = rastizer_state.strip()
                                        existing_value = self.rastizer_state_dictionary.get(rastizer_state_stripped, 0)
                                        self.rastizer_state_dictionary[rastizer_state_stripped] = existing_value + 1

                            elif BLEND_STATE_CALL in call:
                                logger.debug(f'Found blend state on line: {trace_line}')

                                if BLEND_STATE_IDENTIFIER in trace_line:
                                    blend_states_start = trace_line.find(BLEND_STATE_IDENTIFIER) + BLEND_STATE_IDENTIFIER_LENGTH
                                    if self.api == 'D3D10':
                                        blend_states = trace_line[blend_states_start:trace_line.find(BLEND_STATE_IDENTIFIER_END_D3D10,
                                                                                                     blend_states_start)].strip()
                                    elif self.api == 'D3D11':
                                        blend_states = trace_line[blend_states_start:trace_line.find(BLEND_STATE_IDENTIFIER_END_D3D11,
                                                                                                     blend_states_start)].strip()
                                    blend_states = blend_states.split(API_ENTRY_VALUE_DELIMITER)

                                    for blend_state in blend_states:
                                        blend_state_stripped = blend_state.strip()
                                        existing_value = self.blend_state_dictionary.get(blend_state_stripped, 0)
                                        self.blend_state_dictionary[blend_state_stripped] = existing_value + 1

                            elif DEFERRED_CONTEXT_CALL in call and not trace_deffered_context_warned:
                                # issue with apitrace potentially skipping certain call lines if the trace call numbers are not ordered
                                logger.warning('Application is using deffered contexts. Trace parsing may not be accurate.')
                                trace_deffered_context_warned = True

                            elif API_ENTRY_FORMAT_BASE_CALL in call:
                                if FORMAT_IDENTIFIER in trace_line:
                                    logger.debug(f'Found format on line: {trace_line}')

                                    format_start = trace_line.find(FORMAT_IDENTIFIER) + FORMAT_IDENTIFIER_LENGTH
                                    format_value = trace_line[format_start:trace_line.find(API_ENTRY_VALUE_DELIMITER,
                                                                                        format_start)].strip()

                                    existing_value = self.format_dictionary.get(format_value, 0)
                                    self.format_dictionary[format_value] = existing_value + 1

                                if USAGE_IDENTIFIER in trace_line:
                                    logger.debug(f'Found usage on line: {trace_line}')

                                    usage_start = trace_line.find(USAGE_IDENTIFIER) + USAGE_IDENTIFIER_LENGTH
                                    usage_value = trace_line[usage_start:trace_line.find(API_ENTRY_VALUE_DELIMITER,
                                                                                            usage_start)].strip()

                                    if not USAGE_IDENTIFIER_SKIP in usage_value:
                                        existing_value = self.usage_dictionary.get(usage_value, 0)
                                        self.usage_dictionary[usage_value] = existing_value + 1

                                if BIND_FLAGS_IDENTIFIER in trace_line and BIND_FLAGS_SKIP_IDENTIFIER not in trace_line:
                                    logger.debug(f'Found bind flags on line: {trace_line}')

                                    bind_flags_start = trace_line.find(BIND_FLAGS_IDENTIFIER) + BIND_FLAGS_IDENTIFIER_LENGTH
                                    bind_flags = trace_line[bind_flags_start:trace_line.find(API_ENTRY_VALUE_DELIMITER,
                                                                                                bind_flags_start)].strip()

                                    bind_flags = bind_flags.split(BIND_FLAGS_SPLIT_DELIMITER)

                                    for bind_flag in bind_flags:
                                        bind_flag_stripped = bind_flag.strip()
                                        existing_value = self.bind_flag_dictionary.get(bind_flag_stripped, 0)
                                        self.bind_flag_dictionary[bind_flag_stripped] = existing_value + 1

                    else:
                        logger.debug(f'Skipped parsing of line: {trace_line}')

                    if trace_call_counter != trace_call_counter_notification and trace_call_counter % TRACE_LOGGING_CHUNK_CALLS == 0:
                        logger.info(f'Proccessed {trace_call_counter} apitrace calls...')
                        trace_call_counter_notification = trace_call_counter

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

