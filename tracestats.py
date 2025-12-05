#!/usr/bin/env python3
'''
@author: Winter Snowfall
@version: 1.72
@date: 05/12/2025
'''

import os
import json
import logging
import argparse
import subprocess
import queue
import threading
import signal
import shutil

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
TRACE_PARSE_CHUNK_CALLS = 100000
TRACE_PARSE_QUEUE_SIZE = 10
TRACE_LOGGING_CHUNK_CALLS = 10000000
JSON_BASE_KEY = 'tracestats'
JSON_EXPORT_FOLDER_NAME = 'export'
JSON_EXPORT_DEFAULT_FILE_NAME = 'tracestats.json'
SHADER_DUMPS_FOLDER_NAME = 'dumps'
SHADER_DUMPS_CALL_CHUNK_SIZE = 10000

# parsing constants
API_ENTRY_CALLS = {'DirectDrawCreateEx': 'D3D7',
                   'Direct3DCreate8': 'D3D8',
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
API_BASE_CALLS = {**API_ENTRY_CALLS, 'DirectDrawEnumerateExA': 'D3D7',
                                     'CreateDXGIFactory': 'DXGI',
                                     'CreateDXGIFactory1': 'DXGI',
                                     'CreateDXGIFactory2': 'DGXI'}
TRACE_API_OVERRIDES = {'wargame_'   : 'D3D9Ex', # Ignore queries done on a plain D3D9 interface, as it's not used for rendering
                       'xrEngine___': 'D3D10',  # Creates a D3D11 device first, but renders using D3D10
                       'RebelGalaxy': 'D3D11'}  # Creates a D3D10 device first, but renders using D3D11
# To convert, use: int.from_bytes(b'ATOC', 'little') or:
# (1129272385).to_bytes(4, 'little').decode('ascii')
VENDOR_HACK_VALUES = {'1515406674': 'RESZ',        # This is the FOURCC
                      '2141212672': 'RESZ_ENABLE', # This is the enable value, not the FOURCC
                      '1414745673': 'INST',
                      '827142721' : 'A2M1',
                      '810365505' : 'A2M0',
                      # not actually used in conjunction with render states, but will be checked for support
                      '1112945234': 'R2VB',
                      # undocumented ATI/Nvidia centroid hack (alternate pixel center)
                      '1414415683': 'CENT',
                      # Nvidia fast Z reject hack used by older Source engine builds
                      '1093815368': 'HL2A',
                      # undocumented game-specific hacks ###
                      '826953539' : 'COJ1',                # Call of Juarez
                      '808931924' : 'TR70',                # Tomb Raider: Anniversary / Legend
                      '1162692948': 'TIME',                # TimeShift
                      '1282302283': 'KanL',                # Kane & Lynch (2)
                      ######################################
                      '1129272385': 'ATOC',
                      '1094800211': 'SSAA',
                      '1297108803': 'COPM',
                      '1111774798': 'NVDB'}
                       # Checked by D3D9 SAGE engine games
KNOWN_FOURCC_FORMATS = ('EXT1', 'FXT1', 'GXT1', 'HXT1',
                       # Checked by various D3D8 and D3D9 games
                        'AL16', 'AR16', ' R16', ' L16',
                       # FOURCCs specific to Freelancer
                        'DAA1', 'DAA8', 'DAOP', 'DAOT')

API_ENTRY_CALL_IDENTIFIER = '::'
API_ENTRY_VALUE_DELIMITER = ','
SHADER_DUMP_SKIP_IDENTIFIER_D3D8_9 = 'pFunction = NULL'
SHADER_DUMP_SKIP_IDENTIFIER_D3D10_11 = 'pShaderBytecode = NULL'

# D3D7 vertex buffer capability flags
D3DVBCAPS_SYSTEMMEMORY = 0x00000800
D3DVBCAPS_WRITEONLY    = 0x00010000
D3DVBCAPS_OPTIMIZED    = 0x80000000
D3DVBCAPS_DONOTCLIP    = 0x00000001

################################# DDRAW7, D3D7 #################################
# cooperative level flags
COOPERATIVE_LEVEL_FLAGS_CALL = 'IDirectDraw7::SetCooperativeLevel'
COOPERATIVE_LEVEL_FLAGS_IDENTIFIER = 'dwFlags = '
COOPERATIVE_LEVEL_FLAGS_IDENTIFIER_LENGTH = len(COOPERATIVE_LEVEL_FLAGS_IDENTIFIER)
COOPERATIVE_LEVEL_FLAGS_IDENTIFIER_END = ')'
COOPERATIVE_LEVEL_FLAGS_SPLIT_DELIMITER = '|'
# surface caps
SURFACE_CAPS_CALL = 'IDirectDraw7::CreateSurface'
SURFACE_CAPS_IDENTIFIER = 'dwCaps = '
SURFACE_CAPS2_IDENTIFIER = 'dwCaps2 = '
SURFACE_CAPS_IDENTIFIER_LENGTH = len(SURFACE_CAPS_IDENTIFIER)
SURFACE_CAPS2_IDENTIFIER_LENGTH = len(SURFACE_CAPS2_IDENTIFIER)
SURFACE_CAPS_SPLIT_DELIMITER = '|'
SURFACE_CAPS_SKIP_IDENTIFIER = 'dwCaps = 0x0'
SURFACE_CAPS2_SKIP_IDENTIFIER = 'dwCaps2 = 0x0'
# vertex buffer caps
VERTEX_BUFFER_CAPS_CALL = 'IDirect3D7::CreateVertexBuffer'
VERTEX_BUFFER_CAPS_IDENTIFIER = 'dwCaps = '
VERTEX_BUFFER_CAPS_IDENTIFIER_LENGTH = len(SURFACE_CAPS_IDENTIFIER)
VERTEX_BUFFER_CAPS_SPLIT_DELIMITER = '|'
VERTEX_BUFFER_CAPS_SKIP_IDENTIFIER = 'dwCaps = 0x0'
# flip flags
FLIP_FLAGS_CALL = 'IDirectDrawSurface7::Flip'
FLIP_FLAGS_IDENTIFIER = 'dwFlags = '
FLIP_FLAGS_IDENTIFIER_LENGTH = len(FLIP_FLAGS_IDENTIFIER)
FLIP_FLAGS_IDENTIFIER_END = ')'
FLIP_FLAGS_SPLIT_DELIMITER = '|'
FLIP_FLAGS_SKIP_IDENTIFIER = 'dwFlags = 0x0'
# render states
RENDER_STATES_CALL7 = 'IDirect3DDevice7::SetRenderState'
RENDER_STATES_IDENTIFIER7 = 'D3DRENDERSTATE_'
RENDER_STATES_IDENTIFIER7_LENGTH = len(RENDER_STATES_IDENTIFIER7)
RENDER_STATES_IDENTIFIER7_END = ','
# lock flags
LOCK_FLAGS_SURFACE_CALL7 = 'IDirectDrawSurface7::Lock'
LOCK_FLAGS_BUFFER_CALL7 = 'IDirect3DVertexBuffer7::Lock'
LOCK_FLAGS_IDENTIFIER7 = 'dwFlags = '
LOCK_FLAGS_IDENTIFIER7_LENGTH = len(LOCK_FLAGS_IDENTIFIER7)
LOCK_FLAGS_VALUE_IDENTIFIER7 = 'DDLOCK_'
LOCK_FLAGS_SKIP_IDENTIFIER7 = 'dwFlags = 0x0'
LOCK_FLAGS_SPLIT_DELIMITER7 = '|'
# device type
DEVICE_CREATION_CALL7 = 'IDirect3D7::CreateDevice'
DEVICE_TYPE_IDENTIFIER7 = 'rclsid = '
DEVICE_TYPE_IDENTIFIER7_LENGTH = len(DEVICE_TYPE_IDENTIFIER7)
################################# DDRAW7, D3D7 #################################

############################## D3D8, D3D9Ex, D3D9 ##############################
# check device format vendor hacks
CHECK_DEVICE_FORMAT_CALL = '::CheckDeviceFormat'
CHECK_DEVICE_FORMAT_IDENTIFIER = 'CheckFormat = '
CHECK_DEVICE_FORMAT_IDENTIFIER_LENGTH = len(CHECK_DEVICE_FORMAT_IDENTIFIER)
CHECK_DEVICE_FORMAT_IDENTIFIER_END = ')'
# device type
DEVICE_CREATION_CALL = '::CreateDevice'
DEVICE_TYPE_IDENTIFIER = 'DeviceType = '
DEVICE_TYPE_IDENTIFIER_LENGTH = len(DEVICE_TYPE_IDENTIFIER)
# behavior flags
BEHAVIOR_FLAGS_IDENTIFIER = 'BehaviorFlags = '
BEHAVIOR_FLAGS_IDENTIFIER_LENGTH = len(BEHAVIOR_FLAGS_IDENTIFIER)
BEHAVIOR_FLAGS_SPLIT_DELIMITER = '|'
# present parameters
PRESENT_PARAMETERS_IDENTIFIER = 'pPresentationParameters = &{'
PRESENT_PARAMETERS_SKIP_IDENTIFIER = 'pPresentationParameters = ?'
PRESENT_PARAMETERS_IDENTIFIER_LENGTH = len(PRESENT_PARAMETERS_IDENTIFIER)
PRESENT_PARAMETERS_IDENTIFIER_END = '}'
PRESENT_PARAMETERS_SPLIT_DELIMITER = ','
# present parameter flags are handled separately
PRESENT_PARAMETERS_SKIPPED = ('Flags', 'BackBufferWidth', 'BackBufferHeight', 'hDeviceWindow', 'Windowed', 'FullScreen_RefreshRateInHz')
PRESENT_PARAMETERS_VALUE_SPLIT_DELIMITER = ' = '
# present parameter flags
PRESENT_PARAMETER_FLAGS_IDENTIFIER = ', Flags = '
PRESENT_PARAMETER_FLAGS_IDENTIFIER_LENGTH = len(PRESENT_PARAMETER_FLAGS_IDENTIFIER)
PRESENT_PARAMETER_FLAGS_SKIP_IDENTIFIER = ', Flags = 0x0'
PRESENT_PARAMETER_FLAGS_SPLIT_DELIMITER = '|'
# render states
RENDER_STATES_CALL = '::SetRenderState'
RENDER_STATES_IDENTIFIER = 'State = '
RENDER_STATES_IDENTIFIER_LENGTH = len(RENDER_STATES_IDENTIFIER)
# Star Wars: Force Unleashed (2) will set RS = -1 to 1 for some reason...
# Gun Metal will set RS 99, which is undefined...
RENDER_STATES_SKIPPED = ('-1', '99')
# query types
QUERY_TYPE_CALL_D3D8 = '::GetInfo'
QUERY_TYPE_IDENTIFIER_D3D8 = 'DevInfoID = '
QUERY_TYPE_IDENTIFIER_LENGTH_D3D8 = len(QUERY_TYPE_IDENTIFIER_D3D8)
QUERY_TYPE_CALL_D3D9_10_11 = '::CreateQuery'
QUERY_TYPE_IDENTIFIER_D3D9 = 'Type = '
QUERY_TYPE_IDENTIFIER_LENGTH_D3D9 = len(QUERY_TYPE_IDENTIFIER_D3D9)
QUERY_TYPE_IDENTIFIER_D3D10_11 = 'Query = '
QUERY_TYPE_IDENTIFIER_D3D10_11_LENGTH = len(QUERY_TYPE_IDENTIFIER_D3D10_11)
# lock flags
LOCK_FLAGS_CALL = '::Lock'
LOCK_FLAGS_IDENTIFIER = 'Flags = '
LOCK_FLAGS_IDENTIFIER_LENGTH = len(LOCK_FLAGS_IDENTIFIER)
LOCK_FLAGS_IDENTIFIER_END = ')'
LOCK_FLAGS_VALUE_IDENTIFIER = 'D3DLOCK_'
LOCK_FLAGS_SKIP_IDENTIFIER = 'Flags = 0x0'
LOCK_FLAGS_SPLIT_DELIMITER = '|'
# shaders
VERTEX_SHADER_CALL = '::CreateVertexShader'
PIXEL_SHADER_CALL = '::CreatePixelShader'
# D3D10/11 only shader types
COMPUTE_SHADER_CALL = '::CreateComputeShader'
DOMAIN_SHADER_CALL = '::CreateDomainShader'
GEOMETRY_SHADER_CALL = '::CreateGeometryShader'
HULL_SHADER_CALL = '::CreateHullShader'
VERTEX_SHADER_IDENTIFIER = 'vs_'
VERTEX_SHADER_IDENTIFIER_LENGTH = len(VERTEX_SHADER_IDENTIFIER)
PIXEL_SHADER_IDENTIFIER = 'ps_'
PIXEL_SHADER_IDENTIFIER_LENGTH = len(PIXEL_SHADER_IDENTIFIER)
# D3D10/11 only shader types
COMPUTE_SHADER_IDENTIFIER = 'cs_'
COMPUTE_SHADER_IDENTIFIER_LENGTH = len(COMPUTE_SHADER_IDENTIFIER)
DOMAIN_SHADER_IDENTIFIER = 'ds_'
DOMAIN_SHADER_IDENTIFIER_LENGTH = len(DOMAIN_SHADER_IDENTIFIER)
GEOMETRY_SHADER_IDENTIFIER = 'gs_'
GEOMETRY_SHADER_IDENTIFIER_LENGTH = len(GEOMETRY_SHADER_IDENTIFIER)
HULL_SHADER_IDENTIFIER = 'hs_'
HULL_SHADER_IDENTIFIER_LENGTH = len(HULL_SHADER_IDENTIFIER)
SHADER_LINE_WHITESPACE = ' '
SHADER_VERSION_OFFSET = 3 # x_y (x = major version, y = minor version)
SHADER_NO_DISASSEMBLY_D3D8_9 = 'pFunction = blob'
SHADER_NO_DISASSEMBLY_D3D10_11 = 'pShaderBytecode = blob'
# usage
USAGE_IDENTIFIER = 'Usage = '
USAGE_IDENTIFIER_LENGTH = len(USAGE_IDENTIFIER)
USAGE_IDENTIFIER_END_D3D8 = ')'
USAGE_VALUE_IDENTIFIER = 'D3DUSAGE_'
USAGE_SKIP_IDENTIFIER = 'Flags = 0x0'
USAGE_SKIP_IDENTIFIER_D3D10_11 = 'DXGI_USAGE_'
USAGE_SPLIT_DELIMITER = '|'
# formats
API_ENTRY_FORMAT_BASE_CALL = '::Create'
FORMAT_IDENTIFIER = 'Format = '
FORMAT_IDENTIFIER_LENGTH = len(FORMAT_IDENTIFIER)
# pools
POOL_IDENTIFIER = 'Pool = '
POOL_IDENTIFIER_LENGTH = len(POOL_IDENTIFIER)
# vendor hacks
VENDOR_HACK_POINTSIZE = 'State = D3DRS_POINTSIZE,'
VENDOR_HACK_ADAPTIVETESS_X = 'State = D3DRS_ADAPTIVETESS_X,'
VENDOR_HACK_ADAPTIVETESS_Y = 'State = D3DRS_ADAPTIVETESS_Y,'
VENDOR_HACK_IDENTIFIER = 'Value = '
VENDOR_HACK_IDENTIFIER_LENGTH = len(VENDOR_HACK_IDENTIFIER)
VENDOR_HACK_IDENTIFIER_END = ')'
############################## D3D8, D3D9Ex, D3D9 ##############################

################################# D3D10, D3D11 #################################
# device flags (treat these as d3d9 behavior flags for simplicity)
DEVICE_FLAGS_AND_FEATURE_LEVELS_CALL = 'CreateDevice'
DEVICE_FLAGS_IDENTIFIER = 'Flags = '
DEVICE_FLAGS_IDENTIFIER_LENGTH = len(DEVICE_FLAGS_IDENTIFIER)
DEVICE_FLAGS_SKIP_IDENTIFIER = 'Flags = 0x0'
DEVICE_FLAGS_SPLIT_DELIMITER = '|'
# swapchain parameters
SWAPCHAIN_PARAMETERS_CALL = '::CreateSwapChain'
SWAPCHAIN_DEVICE_PARAMETERS_CALL = 'CreateDeviceAndSwapChain'
SWAPCHAIN_PARAMETERS_IDENTIFIER = 'pDesc = &{'
SWAPCHAIN_PARAMETERS_IDENTIFIER_2 = 'pSwapChainDesc = &{'
SWAPCHAIN_PARAMETERS_SKIP_IDENTIFIER = 'pDesc = NULL'
SWAPCHAIN_PARAMETERS_SKIP_IDENTIFIER_2 = 'pSwapChainDesc = NULL'
SWAPCHAIN_PARAMETERS_IDENTIFIER_LENGTH = len(SWAPCHAIN_PARAMETERS_IDENTIFIER)
SWAPCHAIN_PARAMETERS_IDENTIFIER_LENGTH_2 = len(SWAPCHAIN_PARAMETERS_IDENTIFIER_2)
SWAPCHAIN_PARAMETERS_IDENTIFIER_END = '}, pFullscreenDesc ='
SWAPCHAIN_PARAMETERS_IDENTIFIER_END_2 = '}, ppSwapChain ='
SWAPCHAIN_PARAMETERS_SPLIT_DELIMITER = ','
SWAPCHAIN_PARAMETERS_CAPTURED = ('AlphaMode', 'BufferCount', 'BufferUsage', 'Flags', 'Format',
                                 'ScanlineOrdering', 'Quality', 'Count', 'Scaling', 'Stereo', 'SwapEffect')
SWAPCHAIN_PARAMETERS_VALUE_SPLIT_DELIMITER = ' = '
SWAPCHAIN_BUFFER_USAGE_VALUE_SPLIT_DELIMITER = '|'
SWAPCHAIN_FLAGS_VALUE_SPLIT_DELIMITER = '|'
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
RASTIZER_STATE_SKIPPED = ('DepthBias', 'DepthBiasClamp', 'SlopeScaledDepthBias')
RASTIZER_STATE_VALUE_SPLIT_DELIMITER = ' = '
# blend state
BLEND_STATE_CALL = '::CreateBlendState'
BLEND_STATE_IDENTIFIER = 'pBlendStateDesc = &{'
BLEND_STATE_IDENTIFIER_LENGTH = len(RASTIZER_STATE_IDENTIFIER)
BLEND_STATE_IDENTIFIER_END_D3D10 = ', BlendEnable = '
BLEND_STATE_IDENTIFIER_END_D3D11 = ', RenderTarget = '
# bind flags
BIND_FLAGS_IDENTIFIER = 'BindFlags = '
BIND_FLAGS_IDENTIFIER_LENGTH = len(BIND_FLAGS_IDENTIFIER)
BIND_FLAGS_SKIP_IDENTIFIER = 'BindFlags = 0x0'
BIND_FLAGS_SPLIT_DELIMITER = '|'
################################# D3D10, D3D11 #################################

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

    @classmethod
    def detect_potential_vendor_hack(cls, vendor_hack_value_int, trace_line):
        potential_vendor_hack_value = None

        # check for values between 0x7fa00000 and 0x7fa10000, as that seems to have been a
        # range used by ATI/AMD to enable/disable and configure all sort of behavior
        if (VENDOR_HACK_POINTSIZE in trace_line and
            vendor_hack_value_int > 2141192192 and vendor_hack_value_int < 2141257728):
            potential_vendor_hack_value = hex(vendor_hack_value_int)
        # warn for any unexpected values which properly translate to FOURCCs
        else:
            try:
                vendor_hack_fourcc = vendor_hack_value_int.to_bytes(4, 'little').decode('ascii')
                # some values may decode properly but will not be actual FOURCCs
                # also account for whitespace in some FOURCCs, such as for R16
                if vendor_hack_fourcc.strip().isalnum():
                    potential_vendor_hack_value = vendor_hack_fourcc
            except UnicodeDecodeError:
                pass

        return potential_vendor_hack_value

    def __init__(self, trace_input_paths, json_export_path, application_name, application_link,
                 apis_to_skip, shader_dump, apitrace_path, use_wine_for_apitrace):
        if trace_input_paths is not None:
            self.trace_input_paths = trace_input_paths[0]
        else:
            self.trace_input_paths = None

        if json_export_path is None:
            if self.trace_input_paths is None or len(self.trace_input_paths) > 1:
                self.json_export_path = os.path.join(JSON_EXPORT_FOLDER_NAME,
                                                     JSON_EXPORT_DEFAULT_FILE_NAME)
            else:
                trace_file_name = os.path.basename(self.trace_input_paths[0]).rsplit('.', 1)[0]
                # compressed trace name handling
                if trace_file_name.endswith('.trace'):
                    trace_file_name = trace_file_name.rsplit('.', 1)[0]
                self.json_export_path = os.path.join(JSON_EXPORT_FOLDER_NAME, ''.join((trace_file_name, '.json')))
        else:
            self.json_export_path = json_export_path

        if apitrace_path is None:
            self.apitrace_path = shutil.which('apitrace')
            if self.apitrace_path is None:
                logger.critical('Unable to find apitrace. Please ensure it is in $PATH or use -a to specify the full path.')
                raise SystemExit(1)

        else:
            if os.path.isfile(apitrace_path):
                self.apitrace_path = apitrace_path
            else:
                logger.critical('Invalid apitrace path specified.')
                raise SystemExit(2)

        self.use_wine_for_apitrace = use_wine_for_apitrace

        try:
            if self.use_wine_for_apitrace:
                subprocess_params = ('wine', self.apitrace_path, 'version')
            else:
                subprocess_params = (self.apitrace_path, 'version')

            apitrace_check_subprocess = subprocess.run(subprocess_params,
                                                       stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                                       check=True)
            apitrace_check_output = apitrace_check_subprocess.stdout.decode('utf-8').split()

            try:
                logger.debug(f'Using apitrace version {apitrace_check_output[1]}')
                if apitrace_check_output[0] != 'apitrace' and float(apitrace_check_output[1]) < 12.0:
                    logger.critical('Invalid apitrace version. Please use at least apitrace 12.0.')
                    raise SystemExit(3)
            except ValueError:
                logger.critical('Invalid apitrace executable')
                raise SystemExit(4)

        except:
            logger.critical('Invalid apitrace executable')
            raise SystemExit(5)

        if apis_to_skip is not None:
            self.apis_to_skip = [api.strip().upper() if api.strip().upper() != 'D3D9EX' else 'D3D9Ex' for api in apis_to_skip.split(',')]
            logger.info(f'Skiping APIs: {self.apis_to_skip}')
        else:
            self.apis_to_skip = None

        self.shader_dump = shader_dump
        self.compressed_trace = False
        self.binary_name_raw = None
        self.binary_name = None
        self.application_name = application_name
        self.application_link = application_link
        self.traceappnames_api = None
        self.api = None
        self.shader_dump_call_array = []
        self.api_call_dictionary = {}
        self.vendor_hack_check_dictionary = {}
        self.device_type_dictionary = {}
        self.behavior_flag_dictionary = {}
        self.present_parameter_dictionary = {}
        self.present_parameter_flag_dictionary = {}
        self.render_state_dictionary = {}
        self.query_type_dictionary = {}
        self.lock_flag_dictionary = {}
        self.shader_version_dictionary = {}
        self.format_dictionary = {}
        self.vendor_hack_dictionary = {}
        self.pool_dictionary = {}
        self.device_flag_dictionary = {}
        self.swapchain_parameter_dictionary = {}
        self.swapchain_buffer_usage_dictionary = {}
        self.swapchain_flag_dictionary = {}
        self.feature_level_dictionary = {}
        self.rastizer_state_dictionary = {}
        self.blend_state_dictionary = {}
        self.usage_dictionary = {}
        self.bind_flag_dictionary = {}
        self.cooperative_level_flag_dictionary = {}
        self.flip_flag_dictionary = {}
        self.surface_cap_dictionary = {}
        self.vertex_buffer_cap_dictionary = {}

        self.process_queue = queue.Queue(maxsize=TRACE_PARSE_QUEUE_SIZE)
        self.api_skip = threading.Event()
        self.parse_loop = threading.Event()
        self.process_loop = threading.Event()
        self.json_output = {JSON_BASE_KEY: []}

    def process_traces(self):
        for trace_path in self.trace_input_paths:
            if os.path.isfile(trace_path):
                self.traceappnames_api = None
                self.api_skip.clear()

                logger.info(f'Processing trace: {trace_path}')

                self.binary_name_raw, file_extension = os.path.basename(trace_path).rsplit('.', 1)
                if file_extension == 'zst':
                    trace_path_final = os.path.join(os.path.dirname(trace_path), self.binary_name_raw)
                    self.binary_name_raw = self.binary_name = self.binary_name_raw.rsplit('.', 1)[0]
                    self.compressed_trace = True
                else:
                    trace_path_final = trace_path
                    self.binary_name = self.binary_name_raw
                # workaround for renamed generic game/Game.exe apitraces
                if self.binary_name_raw.upper().startswith('GAME'):
                    self.binary_name = self.binary_name_raw[:4]
                # workaround for games with multiple editions or that support multiple APIs
                elif self.binary_name_raw.endswith('_'):
                    while self.binary_name.endswith('_'):
                        self.binary_name = self.binary_name[:-1]

                if self.application_name is not None:
                    logger.info(f'Using application name: {self.application_name}')
                elif TRACEAPPNAMES_IS_IMPORTED:
                    try:
                        self.application_name = TraceAppNames.get(self.binary_name_raw)[0]
                        if self.application_name is not None:
                            logger.info(f'Application name found in traceappnames repository: {self.application_name}')
                    except TypeError:
                        pass
                # use the binary name as an application name if it is undertermined at this point
                if self.application_name is None:
                    logger.info(f'Defaulting application name to: {self.binary_name}')
                    self.application_name = self.binary_name

                if self.application_link is not None:
                    logger.info(f'Using application link: {self.application_link}')
                elif TRACEAPPNAMES_IS_IMPORTED:
                    try:
                        self.application_link = TraceAppNames.get(self.binary_name_raw)[1]
                        if self.application_link is not None:
                            logger.info(f'Application link found in traceappnames repository: {self.application_link}')
                    except TypeError:
                        pass

                if TRACEAPPNAMES_IS_IMPORTED:
                    try:
                        self.traceappnames_api = TraceAppNames.get(self.binary_name_raw)[2]
                        if self.traceappnames_api is not None:
                            logger.info(f'Application API found in traceappnames repository: {self.traceappnames_api}')
                    except TypeError:
                        pass

                    if self.apis_to_skip is not None and self.traceappnames_api in self.apis_to_skip:
                        logger.info('Skipped trace due to API filter')
                        continue

                if self.compressed_trace:
                    try:
                        logger.info('Decompressing trace file...')
                        subprocess.run(['zstd', '-d', '-f', trace_path, '-o', trace_path_final],
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                       check=True)
                    except subprocess.CalledProcessError:
                        logger.critical(f'Unable to decompress trace file: {trace_path}')
                        raise SystemExit(6)

                self.process_loop.set()

                # start trace processing thread
                process_thread = threading.Thread(target=self.trace_parse_worker, args=())
                process_thread.daemon = True
                process_thread.start()

                self.parse_loop.set()

                # mind the -v (verbose) flag here, otherwise apitrace dump will skip various calls :/
                if self.use_wine_for_apitrace:
                    subprocess_params = ('wine', self.apitrace_path, 'dump', '-v', '--color=never', trace_path_final)
                else:
                    subprocess_params = (self.apitrace_path, 'dump', '-v', '--color=never', trace_path_final)

                trace_chunk_line_count = 0
                trace_chunk_lines = []

                try:
                    trace_dump_subprocess = subprocess.Popen(subprocess_params, bufsize=0,
                                                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                                             text=True)

                    while self.parse_loop.is_set():
                        trace_chunk_line = trace_dump_subprocess.stdout.readline()

                        if trace_chunk_line == '' and trace_dump_subprocess.poll() is not None:
                            # flush any pending chunk lines
                            if len(trace_chunk_lines):
                                self.process_queue.put(trace_chunk_lines)
                            self.parse_loop.clear()
                            logger.info('End of trace dump output detected')
                        else:
                            trace_chunk_line_count += 1
                            trace_chunk_lines.append(trace_chunk_line)

                            if trace_chunk_line_count == TRACE_PARSE_CHUNK_CALLS:
                                self.process_queue.put(trace_chunk_lines)
                                trace_chunk_line_count = 0
                                trace_chunk_lines = []

                except:
                    logger.critical('Critical exception during the apitrace dump process')
                    self.parse_loop.clear()

                # signal the termination of the processing thread
                self.process_loop.clear()
                # ensure the process_queue is drained
                self.process_queue.join()
                # ensure the processsing thread has halted
                process_thread.join()

                if not self.api_skip.is_set():
                    if not self.shader_dump:
                        return_dictionary = {}
                        return_dictionary['binary_name'] = self.binary_name
                        return_dictionary['name'] = self.application_name
                        if self.application_link is not None:
                            return_dictionary['link'] = self.application_link
                        if len(self.api_call_dictionary) > 0:
                            return_dictionary['api_calls'] = self.api_call_dictionary
                        if len(self.vendor_hack_check_dictionary) > 0:
                            return_dictionary['vendor_hack_checks'] = self.vendor_hack_check_dictionary
                        if len(self.device_type_dictionary) > 0:
                            return_dictionary['device_types'] = self.device_type_dictionary
                        if len(self.present_parameter_dictionary) > 0:
                            return_dictionary['present_parameters'] = self.present_parameter_dictionary
                        if len(self.present_parameter_flag_dictionary) > 0:
                            return_dictionary['present_parameter_flags'] = self.present_parameter_flag_dictionary
                        if len(self.behavior_flag_dictionary) > 0:
                            return_dictionary['behavior_flags'] = self.behavior_flag_dictionary
                        if len(self.render_state_dictionary) > 0:
                            return_dictionary['render_states'] = self.render_state_dictionary
                        if len(self.query_type_dictionary) > 0:
                            return_dictionary['query_types'] = self.query_type_dictionary
                        if len(self.lock_flag_dictionary) > 0:
                            return_dictionary['lock_flags'] = self.lock_flag_dictionary
                        if len(self.shader_version_dictionary) > 0:
                            return_dictionary['shader_versions'] = self.shader_version_dictionary
                        if len(self.format_dictionary) > 0:
                            return_dictionary['formats'] = self.format_dictionary
                        if len(self.vendor_hack_dictionary) > 0:
                            return_dictionary['vendor_hacks'] = self.vendor_hack_dictionary
                        if len(self.pool_dictionary) > 0:
                            return_dictionary['pools'] = self.pool_dictionary
                        if len(self.device_flag_dictionary) > 0:
                            return_dictionary['device_flags'] = self.device_flag_dictionary
                        if len(self.swapchain_parameter_dictionary) > 0:
                            return_dictionary['swapchain_parameters'] = self.swapchain_parameter_dictionary
                        if len(self.swapchain_buffer_usage_dictionary) > 0:
                            return_dictionary['swapchain_buffer_usage'] = self.swapchain_buffer_usage_dictionary
                        if len(self.swapchain_flag_dictionary) > 0:
                            return_dictionary['swapchain_flags'] = self.swapchain_flag_dictionary
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
                        if len(self.cooperative_level_flag_dictionary) > 0:
                            return_dictionary['cooperative_level_flags'] = self.cooperative_level_flag_dictionary
                        if len(self.flip_flag_dictionary) > 0:
                            return_dictionary['flip_flags'] = self.flip_flag_dictionary
                        if len(self.surface_cap_dictionary) > 0:
                            return_dictionary['surface_caps'] = self.surface_cap_dictionary
                        if len(self.vertex_buffer_cap_dictionary) > 0:
                            return_dictionary['vertex_buffer_caps'] = self.vertex_buffer_cap_dictionary

                        self.json_output[JSON_BASE_KEY].append(return_dictionary)

                    elif len(self.shader_dump_call_array) > 0:
                        logger.info(f'Dumping {len(self.shader_dump_call_array)} shader binaries...')

                        # split the shader dump call numbers into strings of a size equal to SHADER_DUMPS_CALL_CHUNK_SIZE
                        # in order to circumvent the "OSError: [Errno 7] Argument list too long" exception on shader heavy apitraces
                        shader_dump_call_strings = [','.join(self.shader_dump_call_array[chunk:chunk + SHADER_DUMPS_CALL_CHUNK_SIZE])
                                                    for chunk in range(0, len(self.shader_dump_call_array), SHADER_DUMPS_CALL_CHUNK_SIZE)]
                        current_path = os.getcwd()
                        trace_path_final_absolute = os.path.join(current_path, trace_path_final)
                        dump_path_final_absolute = os.path.join(current_path, SHADER_DUMPS_FOLDER_NAME)

                        for shader_dump_call_string in shader_dump_call_strings:
                            logger.debug(f'Dumping shader binaries on calls: {shader_dump_call_string}')

                            if self.use_wine_for_apitrace:
                                subprocess_params = ('wine', self.apitrace_path, 'dump', '--blob', f'--calls={shader_dump_call_string}', trace_path_final_absolute)
                            else:
                                subprocess_params = (self.apitrace_path, 'dump', '--blob', f'--calls={shader_dump_call_string}', trace_path_final_absolute)

                            subprocess.run(subprocess_params, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                            cwd=dump_path_final_absolute, check=True)

                    logger.info('Trace processing complete')
                else:
                    logger.info('Skipped trace due to API filter')

                if self.compressed_trace:
                    try:
                        logger.info('Removing decompressed trace file...')
                        os.remove(trace_path_final)
                    except:
                        logger.error(f'Unable to clean up trace: {trace_path_final}')

                # reset state between processed traces
                self.compressed_trace = False
                self.binary_name_raw = None
                self.binary_name = None
                self.traceappnames_api = None
                self.api = None
                self.shader_dump_call_array = []
                self.api_call_dictionary = {}
                self.vendor_hack_check_dictionary = {}
                self.device_type_dictionary = {}
                self.behavior_flag_dictionary = {}
                self.present_parameter_dictionary = {}
                self.present_parameter_flag_dictionary = {}
                self.render_state_dictionary = {}
                self.query_type_dictionary = {}
                self.lock_flag_dictionary = {}
                self.shader_version_dictionary = {}
                self.format_dictionary = {}
                self.vendor_hack_dictionary = {}
                self.pool_dictionary = {}
                self.device_flag_dictionary = {}
                self.swapchain_parameter_dictionary = {}
                self.swapchain_buffer_usage_dictionary = {}
                self.swapchain_flag_dictionary = {}
                self.feature_level_dictionary = {}
                self.rastizer_state_dictionary = {}
                self.blend_state_dictionary = {}
                self.usage_dictionary = {}
                self.bind_flag_dictionary = {}
                self.cooperative_level_flag_dictionary = {}
                self.flip_flag_dictionary = {}
                self.surface_cap_dictionary = {}
                self.vertex_buffer_cap_dictionary = {}

            else:
                logger.warning(f'File not found, skipping: {trace_path}')

        if not self.shader_dump and len(self.json_output[JSON_BASE_KEY]) > 0:
            json_export = json.dumps(self.json_output, sort_keys=True, indent=4,
                                     separators=(',', ': '), ensure_ascii=False)
            logger.debug(f'JSON export output is: {json_export}')

            if os.path.exists(self.json_export_path):
                backup_path = ''.join((self.json_export_path, '.bak'))
                shutil.copy2(self.json_export_path, backup_path)
                logger.info(f'Existing JSON export backed up as: {backup_path}')

            with open(self.json_export_path, 'w') as file:
                file.write(json_export)

            logger.info(f'JSON export complete')

    def trace_parse_worker(self):

        while self.process_loop.is_set() or not self.process_queue.empty():
            # stop parsing if API skip is engaged
            if self.api_skip.is_set():
                self.parse_loop.clear()
                self.process_loop.clear()
                break

            logger.debug(f'Items in the processing queue: {self.process_queue.qsize()}')

            try:
                trace_chunk_lines = self.process_queue.get(block=True, timeout=5)
                trace_call_counter = 0
                shader_call_context = False

                for trace_line_raw in trace_chunk_lines:
                    trace_line = trace_line_raw.rstrip()

                    #logger.debug(f'Processing line: {trace_line}')

                    # there are, surprisingly, quite a lot of
                    # blank/padding lines in an apitrace dump
                    if trace_line == '':
                        continue
                    # early skip embedded full line comments
                    if trace_line.startswith('//'):
                        logger.debug(f'Skipped parsing of line: {trace_line}')
                        continue

                    shader_line = (trace_line.startswith(SHADER_LINE_WHITESPACE) or
                                   # need to check the actual line start too for any
                                   # shader identifiers as some shaders have no indent
                                   trace_line.startswith(VERTEX_SHADER_IDENTIFIER) or
                                   trace_line.startswith(PIXEL_SHADER_IDENTIFIER) or
                                   trace_line.startswith(COMPUTE_SHADER_IDENTIFIER) or
                                   trace_line.startswith(DOMAIN_SHADER_IDENTIFIER) or
                                   trace_line.startswith(GEOMETRY_SHADER_IDENTIFIER) or
                                   trace_line.startswith(HULL_SHADER_IDENTIFIER))

                    if not shader_line:
                        # no need to do more than 2 splits, as we only need
                        # the trace number and later on the api call name
                        split_line = trace_line.split(maxsplit=2)

                        # unnumbered lines will raise a ValueError
                        try:
                            trace_call_counter = int(split_line[0])
                            logger.debug(f'Found call count: {trace_call_counter}')
                        except ValueError:
                            logger.debug(f'Skipped parsing of line: {trace_line}')
                            continue
                    else:
                        split_line = None

                    if (shader_line or API_ENTRY_CALL_IDENTIFIER in trace_line or
                        any(api_base_call in trace_line for api_base_call in API_BASE_CALLS.keys())):
                        # typically, the API entrypoint can be found
                        # on the fist line of an apitrace
                        if self.api is None and not shader_line:
                            for key, value in API_ENTRY_CALLS.items():
                                if key in split_line[1]:
                                    self.api = value
                                    logger.info(f'Detected API: {self.api}')

                                    if self.traceappnames_api is not None and self.traceappnames_api != self.api:
                                        api_override = TRACE_API_OVERRIDES.get(self.binary_name_raw, None)
                                        if api_override is None:
                                            logger.warning('Traceappnames API value is mismatched from trace')
                                        elif self.traceappnames_api == api_override:
                                            logger.info('Known API value override detected')
                                        else:
                                            logger.error('Unexpected API override value')

                                    # otherwise D3D9 will get added to D3D9Ex, heh
                                    break
                            if self.traceappnames_api is None and self.apis_to_skip is not None and self.api in self.apis_to_skip:
                                self.api_skip.set()
                                break

                        # parse API calls
                        if not shader_line:
                            call = split_line[1].split('(', 1)[0]
                            logger.debug(f'Found call: {call}')

                            existing_value = self.api_call_dictionary.get(call, 0)
                            self.api_call_dictionary[call] = existing_value + 1
                        else:
                            # line starting with shader specific whitespace (not an actual call)
                            call = ''

                        # parse device behavior flags, render states, format
                        # and pool values for DDRAW7 and D3D7 apitraces
                        if self.api =='D3D7':
                            if COOPERATIVE_LEVEL_FLAGS_CALL in call:
                                logger.debug(f'Found cooperative level flags on line: {trace_line}')

                                cooperative_level_flags_start = trace_line.find(COOPERATIVE_LEVEL_FLAGS_IDENTIFIER) + COOPERATIVE_LEVEL_FLAGS_IDENTIFIER_LENGTH
                                cooperative_level_flags = trace_line[cooperative_level_flags_start:trace_line.find(COOPERATIVE_LEVEL_FLAGS_IDENTIFIER_END,
                                                                                                                   cooperative_level_flags_start)].strip()
                                cooperative_level_flags = cooperative_level_flags.split(COOPERATIVE_LEVEL_FLAGS_SPLIT_DELIMITER)

                                for cooperative_level_flag in cooperative_level_flags:
                                    cooperative_level_flag_stripped = cooperative_level_flag.strip()
                                    existing_value = self.cooperative_level_flag_dictionary.get(cooperative_level_flag_stripped, 0)
                                    self.cooperative_level_flag_dictionary[cooperative_level_flag_stripped] = existing_value + 1

                            elif SURFACE_CAPS_CALL in call:
                                logger.debug(f'Found surface caps on line: {trace_line}')

                                if SURFACE_CAPS_SKIP_IDENTIFIER not in trace_line:
                                    surface_caps_start = trace_line.find(SURFACE_CAPS_IDENTIFIER) + SURFACE_CAPS_IDENTIFIER_LENGTH
                                    surface_caps = trace_line[surface_caps_start:trace_line.find(API_ENTRY_VALUE_DELIMITER,
                                                                                                 surface_caps_start)].strip()
                                    surface_caps = surface_caps.split(SURFACE_CAPS_SPLIT_DELIMITER)

                                    for surface_cap in surface_caps:
                                        surface_cap_stripped = surface_cap.strip()
                                        existing_value = self.surface_cap_dictionary.get(surface_cap_stripped, 0)
                                        self.surface_cap_dictionary[surface_cap_stripped] = existing_value + 1

                                if SURFACE_CAPS2_SKIP_IDENTIFIER not in trace_line:
                                    surface_caps2_start = trace_line.find(SURFACE_CAPS2_IDENTIFIER) + SURFACE_CAPS2_IDENTIFIER_LENGTH
                                    surface_caps2 = trace_line[surface_caps2_start:trace_line.find(API_ENTRY_VALUE_DELIMITER,
                                                                                                   surface_caps2_start)].strip()
                                    surface_caps2 = surface_caps2.split(SURFACE_CAPS_SPLIT_DELIMITER)

                                    for surface_cap2 in surface_caps2:
                                        surface_cap2_stripped = surface_cap2.strip()
                                        existing_value = self.surface_cap_dictionary.get(surface_cap2_stripped, 0)
                                        self.surface_cap_dictionary[surface_cap2_stripped] = existing_value + 1

                            elif VERTEX_BUFFER_CAPS_CALL in call:
                                logger.debug(f'Found vertex buffer caps on line: {trace_line}')

                                if VERTEX_BUFFER_CAPS_SKIP_IDENTIFIER not in trace_line:
                                    vertex_buffer_caps_start = trace_line.find(VERTEX_BUFFER_CAPS_IDENTIFIER) + VERTEX_BUFFER_CAPS_IDENTIFIER_LENGTH
                                    vertex_buffer_caps = trace_line[vertex_buffer_caps_start:trace_line.find(API_ENTRY_VALUE_DELIMITER,
                                                                                                             vertex_buffer_caps_start)].strip()
                                    #vertex_buffer_caps = vertex_buffer_caps.split(VERTEX_BUFFER_CAPS_SPLIT_DELIMITER)
                                    vertex_buffer_caps = int(vertex_buffer_caps)

                                    # apitrace does not currently convert any of these, so we'll have to do it ourselves
                                    vertex_buffer_caps_actual = []
                                    if vertex_buffer_caps & D3DVBCAPS_SYSTEMMEMORY:
                                        vertex_buffer_caps_actual.append('D3DVBCAPS_SYSTEMMEMORY')
                                    if vertex_buffer_caps & D3DVBCAPS_WRITEONLY:
                                        vertex_buffer_caps_actual.append('D3DVBCAPS_WRITEONLY')
                                    if vertex_buffer_caps & D3DVBCAPS_OPTIMIZED:
                                        vertex_buffer_caps_actual.append('D3DVBCAPS_OPTIMIZED')
                                    if vertex_buffer_caps & D3DVBCAPS_DONOTCLIP:
                                        vertex_buffer_caps_actual.append('D3DVBCAPS_DONOTCLIP')

                                    for vertex_buffer_cap in vertex_buffer_caps_actual:
                                        vertex_buffer_cap_stripped = vertex_buffer_cap.strip()
                                        existing_value = self.vertex_buffer_cap_dictionary.get(vertex_buffer_cap_stripped, 0)
                                        self.vertex_buffer_cap_dictionary[vertex_buffer_cap_stripped] = existing_value + 1

                            elif FLIP_FLAGS_CALL in call:
                                logger.debug(f'Found flip flags on line: {trace_line}')

                                if FLIP_FLAGS_SKIP_IDENTIFIER not in trace_line:
                                    flip_flags_start = trace_line.find(FLIP_FLAGS_IDENTIFIER) + FLIP_FLAGS_IDENTIFIER_LENGTH
                                    flip_flags = trace_line[flip_flags_start:trace_line.find(FLIP_FLAGS_IDENTIFIER_END,
                                                                                            flip_flags_start)].strip()
                                    flip_flags = flip_flags.split(FLIP_FLAGS_SPLIT_DELIMITER)

                                    for flip_flag in flip_flags:
                                        flip_flag_stripped = flip_flag.strip()
                                        existing_value = self.flip_flag_dictionary.get(flip_flag_stripped, 0)
                                        self.flip_flag_dictionary[flip_flag_stripped] = existing_value + 1

                            elif LOCK_FLAGS_SURFACE_CALL7 in call or LOCK_FLAGS_BUFFER_CALL7 in call:
                                logger.debug(f'Found lock flags on line: {trace_line}')

                                # IDirectDrawSurface7::Lock actually has two sets of dwFlags, with the latter
                                # being the one related to the actual locks, and what we are interested in
                                if LOCK_FLAGS_SKIP_IDENTIFIER7 not in trace_line:
                                    lock_flags_start = trace_line.rfind(LOCK_FLAGS_IDENTIFIER7) + LOCK_FLAGS_IDENTIFIER7_LENGTH
                                    lock_flags = trace_line[lock_flags_start:trace_line.find(API_ENTRY_VALUE_DELIMITER,
                                                                                             lock_flags_start)].strip()

                                    lock_flags = lock_flags.split(LOCK_FLAGS_SPLIT_DELIMITER7)

                                    for lock_flag in lock_flags:
                                        lock_flag_stripped = lock_flag.strip()

                                        # Praetorians sets several bogus lock values (not part of the enum)
                                        if lock_flag_stripped.startswith(LOCK_FLAGS_VALUE_IDENTIFIER7):
                                            existing_value = self.lock_flag_dictionary.get(lock_flag_stripped, 0)
                                            self.lock_flag_dictionary[lock_flag_stripped] = existing_value + 1

                            elif RENDER_STATES_CALL7 in call:
                                logger.debug(f'Found render states on line: {trace_line}')

                                render_state_start = trace_line.find(RENDER_STATES_IDENTIFIER7)
                                if render_state_start != -1:
                                    render_state_start += RENDER_STATES_IDENTIFIER7_LENGTH
                                    render_state = RENDER_STATES_IDENTIFIER7 + trace_line[render_state_start:trace_line.find(API_ENTRY_VALUE_DELIMITER,
                                                                                                                             render_state_start)].strip()

                                    existing_value = self.render_state_dictionary.get(render_state, 0)
                                    self.render_state_dictionary[render_state] = existing_value + 1

                            elif DEVICE_CREATION_CALL7 in call:
                                logger.debug(f'Found device type flags on line: {trace_line}')

                                device_type_start = trace_line.find(DEVICE_TYPE_IDENTIFIER7) + DEVICE_TYPE_IDENTIFIER7_LENGTH
                                device_type = trace_line[device_type_start:trace_line.find(API_ENTRY_VALUE_DELIMITER,
                                                                                           device_type_start)].strip()

                                existing_value = self.device_type_dictionary.get(device_type, 0)
                                self.device_type_dictionary[device_type] = existing_value + 1

                        # parse device behavior flags, render states, format
                        # and pool values for D3D8, D3D9Ex, and D3D9 apitraces
                        elif self.api == 'D3D8' or self.api == 'D3D9Ex' or self.api == 'D3D9':
                            if CHECK_DEVICE_FORMAT_CALL in call:
                                check_device_format_start = trace_line.find(CHECK_DEVICE_FORMAT_IDENTIFIER) + CHECK_DEVICE_FORMAT_IDENTIFIER_LENGTH
                                check_device_format_value = trace_line[check_device_format_start:trace_line.find(CHECK_DEVICE_FORMAT_IDENTIFIER_END,
                                                                                                                 check_device_format_start)].strip()

                                # decoded D3DFORMAT values (for regular CheckDeviceFormat queries) should be skipped
                                if check_device_format_value.isdigit():
                                    logger.debug(f'CheckDeviceFormat call with numeric format value: {check_device_format_value}')

                                    check_device_format_value_int = int(check_device_format_value)

                                    if check_device_format_value in VENDOR_HACK_VALUES.keys():
                                        logger.debug(f'Found vendor hack check on line: {trace_line}')
                                        vendor_hack_format_value_lookup = VENDOR_HACK_VALUES[check_device_format_value]
                                        vendor_hack_format_value_decoded = ''.join((CHECK_DEVICE_FORMAT_IDENTIFIER, vendor_hack_format_value_lookup))

                                        existing_value = self.vendor_hack_check_dictionary.get(vendor_hack_format_value_decoded, 0)
                                        self.vendor_hack_check_dictionary[vendor_hack_format_value_decoded] = existing_value + 1
                                    elif check_device_format_value_int > 0:
                                        potential_vendor_hack_format_value = self.detect_potential_vendor_hack(check_device_format_value_int, trace_line)

                                        if potential_vendor_hack_format_value is not None and potential_vendor_hack_format_value not in KNOWN_FOURCC_FORMATS:
                                            logger.warning(f'Detected a check for a FOURCC/potential vendor hack value: {potential_vendor_hack_format_value}')

                            elif DEVICE_CREATION_CALL in call:
                                logger.debug(f'Found device type, behavior flags and present parameters on line: {trace_line}')

                                device_type_start = trace_line.find(DEVICE_TYPE_IDENTIFIER) + DEVICE_TYPE_IDENTIFIER_LENGTH
                                device_type = trace_line[device_type_start:trace_line.find(API_ENTRY_VALUE_DELIMITER,
                                                                                           device_type_start)].strip()

                                existing_value = self.device_type_dictionary.get(device_type, 0)
                                self.device_type_dictionary[device_type] = existing_value + 1

                                behavior_flags_start = trace_line.find(BEHAVIOR_FLAGS_IDENTIFIER) + BEHAVIOR_FLAGS_IDENTIFIER_LENGTH
                                behavior_flags = trace_line[behavior_flags_start:trace_line.find(API_ENTRY_VALUE_DELIMITER,
                                                                                                 behavior_flags_start)].strip()
                                behavior_flags = behavior_flags.split(BEHAVIOR_FLAGS_SPLIT_DELIMITER)

                                for behavior_flag in behavior_flags:
                                    behavior_flag_stripped = behavior_flag.strip()
                                    existing_value = self.behavior_flag_dictionary.get(behavior_flag_stripped, 0)
                                    self.behavior_flag_dictionary[behavior_flag_stripped] = existing_value + 1

                                if PRESENT_PARAMETERS_SKIP_IDENTIFIER not in trace_line:
                                    if PRESENT_PARAMETER_FLAGS_SKIP_IDENTIFIER not in trace_line:
                                        present_parameter_flags_start = trace_line.find(PRESENT_PARAMETER_FLAGS_IDENTIFIER) + PRESENT_PARAMETER_FLAGS_IDENTIFIER_LENGTH
                                        present_parameter_flags = trace_line[present_parameter_flags_start:trace_line.find(API_ENTRY_VALUE_DELIMITER,
                                                                                                                           present_parameter_flags_start)].strip()
                                        present_parameter_flags = present_parameter_flags.split(PRESENT_PARAMETER_FLAGS_SPLIT_DELIMITER)

                                        for present_parameter_flag in present_parameter_flags:
                                            present_parameter_flag_stripped = present_parameter_flag.strip()
                                            existing_value = self.present_parameter_flag_dictionary.get(present_parameter_flag_stripped, 0)
                                            self.present_parameter_flag_dictionary[present_parameter_flag_stripped] = existing_value + 1

                                    present_parameters_start = trace_line.find(PRESENT_PARAMETERS_IDENTIFIER) + PRESENT_PARAMETERS_IDENTIFIER_LENGTH
                                    present_parameters = trace_line[present_parameters_start:trace_line.find(PRESENT_PARAMETERS_IDENTIFIER_END,
                                                                                                             present_parameters_start)].strip()
                                    present_parameters = present_parameters.split(PRESENT_PARAMETERS_SPLIT_DELIMITER)

                                    for present_parameter in present_parameters:
                                        present_parameter_stripped = present_parameter.strip()
                                        present_parameter_key, present_parameter_value = present_parameter_stripped.split(PRESENT_PARAMETERS_VALUE_SPLIT_DELIMITER)

                                        if present_parameter_key not in PRESENT_PARAMETERS_SKIPPED:
                                            existing_value = self.present_parameter_dictionary.get(present_parameter_stripped, 0)
                                            self.present_parameter_dictionary[present_parameter_stripped] = existing_value + 1

                            elif RENDER_STATES_CALL in call:
                                logger.debug(f'Found render states on line: {trace_line}')

                                render_state_start = trace_line.find(RENDER_STATES_IDENTIFIER) + RENDER_STATES_IDENTIFIER_LENGTH
                                render_state = trace_line[render_state_start:trace_line.find(API_ENTRY_VALUE_DELIMITER,
                                                                                             render_state_start)].strip()

                                if render_state not in RENDER_STATES_SKIPPED:
                                    existing_value = self.render_state_dictionary.get(render_state, 0)
                                    self.render_state_dictionary[render_state] = existing_value + 1

                                render_state_point_size = VENDOR_HACK_POINTSIZE in trace_line
                                render_state_adaptivetess_x = VENDOR_HACK_ADAPTIVETESS_X in trace_line
                                render_state_adaptivetess_y = VENDOR_HACK_ADAPTIVETESS_Y in trace_line

                                if render_state_point_size or render_state_adaptivetess_x or render_state_adaptivetess_y:
                                    vendor_hack_start = trace_line.find(VENDOR_HACK_IDENTIFIER) + VENDOR_HACK_IDENTIFIER_LENGTH
                                    vendor_hack_value = trace_line[vendor_hack_start:trace_line.find(VENDOR_HACK_IDENTIFIER_END,
                                                                                                     vendor_hack_start)].strip()

                                    if render_state_point_size:
                                        vendor_hack_render_state = 'D3DRS_POINTSIZE = '
                                    elif render_state_adaptivetess_x:
                                        vendor_hack_render_state = 'D3DRS_ADAPTIVETESS_X = '
                                    elif render_state_adaptivetess_y:
                                        vendor_hack_render_state = 'D3DRS_ADAPTIVETESS_Y = '

                                    vendor_hack_value_int = int(vendor_hack_value)

                                    if vendor_hack_value in VENDOR_HACK_VALUES.keys():
                                        logger.debug(f'Found vendor hack on line: {trace_line}')

                                        vendor_hack_value_lookup = VENDOR_HACK_VALUES[vendor_hack_value]
                                        vendor_hack_value_decoded = ''.join((vendor_hack_render_state, vendor_hack_value_lookup))
                                        existing_value = self.vendor_hack_dictionary.get(vendor_hack_value_decoded, 0)
                                        self.vendor_hack_dictionary[vendor_hack_value_decoded] = existing_value + 1
                                    elif vendor_hack_value_int > 0:
                                        potential_vendor_hack_value = self.detect_potential_vendor_hack(vendor_hack_value_int, trace_line)

                                        if potential_vendor_hack_value is not None:
                                            logger.warning(f'Detected a potential vendor hack value: {potential_vendor_hack_value}')

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

                            # D3D9Ex/D3D9 use IDirect3DQuery9::CreateQuery to initiate queries
                            elif (self.api == 'D3D9Ex' or self.api == 'D3D9') and QUERY_TYPE_CALL_D3D9_10_11 in call:
                                logger.debug(f'Found query type on line: {trace_line}')

                                query_type_start = trace_line.find(QUERY_TYPE_IDENTIFIER_D3D9) + QUERY_TYPE_IDENTIFIER_LENGTH_D3D9
                                query_type = trace_line[query_type_start:trace_line.find(API_ENTRY_VALUE_DELIMITER,
                                                                                         query_type_start)].strip()

                                existing_value = self.query_type_dictionary.get(query_type, 0)
                                self.query_type_dictionary[query_type] = existing_value + 1

                            elif LOCK_FLAGS_CALL in call:
                                logger.debug(f'Found lock flags on line: {trace_line}')

                                if LOCK_FLAGS_SKIP_IDENTIFIER not in trace_line:
                                    lock_flags_start = trace_line.find(LOCK_FLAGS_IDENTIFIER) + LOCK_FLAGS_IDENTIFIER_LENGTH
                                    lock_flags = trace_line[lock_flags_start:trace_line.find(LOCK_FLAGS_IDENTIFIER_END,
                                                                                            lock_flags_start)].strip()

                                    lock_flags = lock_flags.split(LOCK_FLAGS_SPLIT_DELIMITER)

                                    for lock_flag in lock_flags:
                                        lock_flag_stripped = lock_flag.strip()

                                        # Mafia sets several bogus lock values (not part of the enum)
                                        if lock_flag_stripped.startswith(LOCK_FLAGS_VALUE_IDENTIFIER):
                                            existing_value = self.lock_flag_dictionary.get(lock_flag_stripped, 0)
                                            self.lock_flag_dictionary[lock_flag_stripped] = existing_value + 1

                            # shader version identifiers can either be part of CreateVertexShader/CreatePixelShader
                            # calls, or included as part of an additional line below those calls in apitrace dumps
                            elif VERTEX_SHADER_CALL in call or PIXEL_SHADER_CALL in call or shader_line:
                                logger.debug(f'Found shader on line: {trace_line}')

                                # not having a shader line means it's a shader creation call
                                if not shader_line:
                                    if self.shader_dump and trace_call_counter > 0 and SHADER_DUMP_SKIP_IDENTIFIER_D3D8_9 not in trace_line:
                                        self.shader_dump_call_array.append(str(trace_call_counter))

                                    # shader dissasebly can fail, in which case apitrace will dump bytecode blobs
                                    if not SHADER_NO_DISASSEMBLY_D3D8_9 in trace_line:
                                        if not shader_call_context:
                                            shader_call_context = True
                                        else:
                                            logger.warning('Shader call context already detected')
                                    else:
                                        logger.warning('Unable to parse shader version due to bytecode dump')

                                # don't do any parsing unless a shader creation call has been detected
                                if shader_call_context:
                                    # strip any comments from a shader line
                                    if shader_line:
                                        trace_line = trace_line.split('//')[0].rstrip()

                                    # D3D8 handles FVF thourgh CreateVertexShader, and there is no way to
                                    # track these otherwise, so treat them as 'vs_fvf' shader versions instead
                                    if self.api == 'D3D8' and VERTEX_SHADER_CALL in call and 'pFunction = NULL' in trace_line:
                                        shader_version = 'vs_fvf'
                                        logger.debug(f'Shader version: {shader_version}')

                                        existing_value = self.shader_version_dictionary.get(shader_version, 0)
                                        self.shader_version_dictionary[shader_version] = existing_value + 1

                                        shader_call_context = False

                                    else:
                                        shader_version = None

                                        shader_version_start_vertex = trace_line.find(VERTEX_SHADER_IDENTIFIER)
                                        shader_version_start_pixel = trace_line.find(PIXEL_SHADER_IDENTIFIER)

                                        if shader_version_start_vertex != -1:
                                            shader_version = trace_line[shader_version_start_vertex:shader_version_start_vertex +
                                                                                                    VERTEX_SHADER_IDENTIFIER_LENGTH +
                                                                                                    SHADER_VERSION_OFFSET]
                                        elif shader_version_start_pixel != -1:
                                            shader_version = trace_line[shader_version_start_pixel:shader_version_start_pixel +
                                                                                                PIXEL_SHADER_IDENTIFIER_LENGTH +
                                                                                                SHADER_VERSION_OFFSET]

                                        # count '_' occurances to filter out some potentially dubious string matches
                                        if shader_version is not None and shader_version.count('_') == 2:
                                            logger.debug(f'Shader version: {shader_version}')

                                            existing_value = self.shader_version_dictionary.get(shader_version, 0)
                                            self.shader_version_dictionary[shader_version] = existing_value + 1

                                            shader_call_context = False
                                else:
                                    logger.debug(f'Skipped parsing of shader line: {trace_line}')

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

                                    if USAGE_SKIP_IDENTIFIER not in trace_line:
                                        usage_start = trace_line.find(USAGE_IDENTIFIER) + USAGE_IDENTIFIER_LENGTH
                                        # Usually, usage values will end on a comma
                                        usage_end = trace_line.find(API_ENTRY_VALUE_DELIMITER, usage_start)
                                        # In D3D8, usage values are also included in CreateVertexShader
                                        # calls, where they sit at the end of the parameter list
                                        if usage_end == -1:
                                            usage_end = trace_line.find(USAGE_IDENTIFIER_END_D3D8, usage_start)
                                        usage_values = trace_line[usage_start:usage_end].strip()
                                        usage_values = usage_values.split(USAGE_SPLIT_DELIMITER)

                                        for usage_value in usage_values:
                                            usage_value_stripped = usage_value.strip()
                                            if usage_value_stripped.startswith(USAGE_VALUE_IDENTIFIER):
                                                existing_value = self.usage_dictionary.get(usage_value_stripped, 0)
                                                self.usage_dictionary[usage_value_stripped] = existing_value + 1

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

                            # need to cater for 'CreateDeviceAndSwapChain' parameters parsing too, so no elif
                            if SWAPCHAIN_PARAMETERS_CALL in call or SWAPCHAIN_DEVICE_PARAMETERS_CALL in call:
                                logger.debug(f'Found swapchain parameters on line: {trace_line}')

                                if SWAPCHAIN_PARAMETERS_SKIP_IDENTIFIER not in trace_line and SWAPCHAIN_PARAMETERS_SKIP_IDENTIFIER_2 not in trace_line:
                                    swapchain_parameters_position = trace_line.find(SWAPCHAIN_PARAMETERS_IDENTIFIER)
                                    swapchain_parameters_variant = SWAPCHAIN_PARAMETERS_IDENTIFIER if swapchain_parameters_position != -1 else SWAPCHAIN_PARAMETERS_IDENTIFIER_2
                                    swapchain_parameters_length_variant = SWAPCHAIN_PARAMETERS_IDENTIFIER_LENGTH if swapchain_parameters_position != -1 else SWAPCHAIN_PARAMETERS_IDENTIFIER_LENGTH_2

                                    swapchain_parameters_end_position = trace_line.find(SWAPCHAIN_PARAMETERS_IDENTIFIER_END)
                                    swapchain_parameters_end_variant = SWAPCHAIN_PARAMETERS_IDENTIFIER_END if swapchain_parameters_end_position != -1 else SWAPCHAIN_PARAMETERS_IDENTIFIER_END_2


                                    swapchain_parameters_start = trace_line.find(swapchain_parameters_variant) + swapchain_parameters_length_variant
                                    swapchain_parameters = trace_line[swapchain_parameters_start:trace_line.find(swapchain_parameters_end_variant,
                                                                                                                 swapchain_parameters_start)].strip()
                                    # we need to strip the the desc for any array flags and add split delimiters
                                    swapchain_parameters = swapchain_parameters.replace('{', SWAPCHAIN_PARAMETERS_SPLIT_DELIMITER).replace('}', SWAPCHAIN_PARAMETERS_SPLIT_DELIMITER)
                                    swapchain_parameters = swapchain_parameters.split(SWAPCHAIN_PARAMETERS_SPLIT_DELIMITER)

                                    for swapchain_parameter in swapchain_parameters:
                                        swapchain_parameter_stripped = swapchain_parameter.strip()

                                        try:
                                            swapchain_parameter_key, swapchain_parameter_value = swapchain_parameter_stripped.split(SWAPCHAIN_PARAMETERS_VALUE_SPLIT_DELIMITER, 1)

                                            if swapchain_parameter_key in SWAPCHAIN_PARAMETERS_CAPTURED:
                                                if swapchain_parameter_value != '0x0':
                                                    if swapchain_parameter_key == 'BufferUsage':
                                                        swapchain_buffer_usage = swapchain_parameter_value.split(SWAPCHAIN_BUFFER_USAGE_VALUE_SPLIT_DELIMITER)

                                                        for swapchain_buffer_usage_flag in swapchain_buffer_usage:
                                                            swapchian_buffer_usage_flag_stripped = swapchain_buffer_usage_flag.strip()

                                                            existing_value = self.swapchain_buffer_usage_dictionary.get(swapchian_buffer_usage_flag_stripped, 0)
                                                            self.swapchain_buffer_usage_dictionary[swapchian_buffer_usage_flag_stripped] = existing_value + 1

                                                    elif swapchain_parameter_key == 'Flags':
                                                        swapchain_flags = swapchain_parameter_value.split(SWAPCHAIN_FLAGS_VALUE_SPLIT_DELIMITER)

                                                        for swapchain_flag in swapchain_flags:
                                                            swapchain_flag_stripped = swapchain_flag.strip()

                                                            existing_value = self.swapchain_flag_dictionary.get(swapchain_flag_stripped, 0)
                                                            self.swapchain_flag_dictionary[swapchain_flag_stripped] = existing_value + 1

                                                    else:
                                                        if swapchain_parameter_key == 'Count' or swapchain_parameter_key == 'Quality':
                                                            swapchain_parameter_stripped = ' '.join(('SampleDesc', swapchain_parameter_stripped))

                                                        existing_value = self.swapchain_parameter_dictionary.get(swapchain_parameter_stripped, 0)
                                                        self.swapchain_parameter_dictionary[swapchain_parameter_stripped] = existing_value + 1
                                        except ValueError:
                                            pass

                            elif QUERY_TYPE_CALL_D3D9_10_11 in call:
                                logger.debug(f'Found query type on line: {trace_line}')

                                query_type_start = trace_line.find(QUERY_TYPE_IDENTIFIER_D3D10_11) + QUERY_TYPE_IDENTIFIER_D3D10_11_LENGTH
                                query_type = trace_line[query_type_start:trace_line.find(API_ENTRY_VALUE_DELIMITER,
                                                                                         query_type_start)].strip()

                                existing_value = self.query_type_dictionary.get(query_type, 0)
                                self.query_type_dictionary[query_type] = existing_value + 1

                            elif RASTIZER_STATE_CALL in call:
                                logger.debug(f'Found rastizer state on line: {trace_line}')

                                if RASTIZER_STATE_IDENTIFIER in trace_line:
                                    rastizer_states_start = trace_line.find(RASTIZER_STATE_IDENTIFIER) + RASTIZER_STATE_IDENTIFIER_LENGTH
                                    rastizer_states = trace_line[rastizer_states_start:trace_line.find(RASTIZER_STATE_IDENTIFIER_END,
                                                                                                       rastizer_states_start)].strip()
                                    rastizer_states = rastizer_states.split(API_ENTRY_VALUE_DELIMITER)

                                    for rastizer_state in rastizer_states:
                                        rastizer_state_stripped = rastizer_state.strip()
                                        rastizer_state_key, rastizer_state_value = rastizer_state_stripped.split(RASTIZER_STATE_VALUE_SPLIT_DELIMITER)

                                        if rastizer_state_key not in RASTIZER_STATE_SKIPPED:
                                            existing_value = self.rastizer_state_dictionary.get(rastizer_state_stripped, 0)
                                            self.rastizer_state_dictionary[rastizer_state_stripped] = existing_value + 1

                            elif BLEND_STATE_CALL in call:
                                logger.debug(f'Found blend state on line: {trace_line}')

                                if BLEND_STATE_IDENTIFIER in trace_line:
                                    blend_states_start = trace_line.find(BLEND_STATE_IDENTIFIER) + BLEND_STATE_IDENTIFIER_LENGTH
                                    blend_states_end = trace_line.find(BLEND_STATE_IDENTIFIER_END_D3D11, blend_states_start)

                                    # if the D3D11 end identifier is not found, look up the D3D10 end indetifier
                                    if blend_states_end == -1:
                                        blend_states_end = trace_line.find(BLEND_STATE_IDENTIFIER_END_D3D10, blend_states_start)

                                    blend_states = trace_line[blend_states_start:blend_states_end].strip()
                                    blend_states = blend_states.split(API_ENTRY_VALUE_DELIMITER)

                                    for blend_state in blend_states:
                                        blend_state_stripped = blend_state.strip()
                                        existing_value = self.blend_state_dictionary.get(blend_state_stripped, 0)
                                        self.blend_state_dictionary[blend_state_stripped] = existing_value + 1

                            # shader version identifiers can either be part of CreateVertexShader/CreatePixelShader
                            # calls, or included as part of an additional line below those calls in apitrace dumps
                            elif (VERTEX_SHADER_CALL in call or PIXEL_SHADER_CALL in call or
                                  COMPUTE_SHADER_CALL in call or DOMAIN_SHADER_CALL in call or
                                  GEOMETRY_SHADER_CALL in call or HULL_SHADER_CALL in call or shader_line):
                                logger.debug(f'Found shader on line: {trace_line}')

                                # not having a shader line means it's a shader creation call
                                if not shader_line:
                                    if self.shader_dump and trace_call_counter > 0 and SHADER_DUMP_SKIP_IDENTIFIER_D3D10_11 not in trace_line:
                                        self.shader_dump_call_array.append(str(trace_call_counter))

                                    # shader dissasebly can fail, in which case apitrace will dump bytecode blobs
                                    if not SHADER_NO_DISASSEMBLY_D3D10_11 in trace_line:
                                        if not shader_call_context:
                                            shader_call_context = True
                                        else:
                                            logger.warning('Shader call context already detected')
                                    else:
                                        logger.warning('Unable to parse shader version due to bytecode dump')

                                # don't do any parsing unless a shader creation call has been detected
                                if shader_call_context:
                                    # strip any comments from a shader line
                                    if shader_line:
                                        trace_line = trace_line.split('//')[0].rstrip()

                                    shader_version = None

                                    shader_version_start_vertex = trace_line.find(VERTEX_SHADER_IDENTIFIER)
                                    shader_version_start_pixel = trace_line.find(PIXEL_SHADER_IDENTIFIER)
                                    shader_version_start_compute = trace_line.find(COMPUTE_SHADER_IDENTIFIER)
                                    shader_version_start_domain = trace_line.find(DOMAIN_SHADER_IDENTIFIER)
                                    shader_version_start_geometry = trace_line.find(GEOMETRY_SHADER_IDENTIFIER)
                                    shader_version_start_hull = trace_line.find(HULL_SHADER_IDENTIFIER)

                                    if shader_version_start_vertex != -1:
                                        shader_version = trace_line[shader_version_start_vertex:shader_version_start_vertex +
                                                                                                VERTEX_SHADER_IDENTIFIER_LENGTH +
                                                                                                SHADER_VERSION_OFFSET]
                                    elif shader_version_start_pixel != -1:
                                        shader_version = trace_line[shader_version_start_pixel:shader_version_start_pixel +
                                                                                            PIXEL_SHADER_IDENTIFIER_LENGTH +
                                                                                            SHADER_VERSION_OFFSET]
                                    elif shader_version_start_compute != -1:
                                        shader_version = trace_line[shader_version_start_compute:shader_version_start_compute +
                                                                                                COMPUTE_SHADER_IDENTIFIER_LENGTH +
                                                                                                SHADER_VERSION_OFFSET]
                                    elif shader_version_start_domain != -1:
                                        shader_version = trace_line[shader_version_start_domain:shader_version_start_domain +
                                                                                                DOMAIN_SHADER_IDENTIFIER_LENGTH +
                                                                                                SHADER_VERSION_OFFSET]
                                    elif shader_version_start_geometry != -1:
                                        shader_version = trace_line[shader_version_start_geometry:shader_version_start_geometry +
                                                                                                GEOMETRY_SHADER_IDENTIFIER_LENGTH +
                                                                                                SHADER_VERSION_OFFSET]
                                    elif shader_version_start_hull != -1:
                                        shader_version = trace_line[shader_version_start_hull:shader_version_start_hull +
                                                                                            HULL_SHADER_IDENTIFIER_LENGTH +
                                                                                            SHADER_VERSION_OFFSET]

                                    # count '_' occurances to filter out some potentially dubious string matches
                                    if shader_version is not None and shader_version.count('_') == 2:
                                        logger.debug(f'Shader version: {shader_version}')

                                        existing_value = self.shader_version_dictionary.get(shader_version, 0)
                                        self.shader_version_dictionary[shader_version] = existing_value + 1

                                        shader_call_context = False
                                else:
                                    logger.debug(f'Skipped parsing of shader line: {trace_line}')

                            elif API_ENTRY_FORMAT_BASE_CALL in call:
                                if FORMAT_IDENTIFIER in trace_line:
                                    logger.debug(f'Found format on line: {trace_line}')

                                    format_start = trace_line.find(FORMAT_IDENTIFIER) + FORMAT_IDENTIFIER_LENGTH
                                    format_value = trace_line[format_start:trace_line.find(API_ENTRY_VALUE_DELIMITER,
                                                                                           format_start)].strip()

                                    # at times the format value can end in a '},' block
                                    format_value = format_value.replace('}', '')

                                    existing_value = self.format_dictionary.get(format_value, 0)
                                    self.format_dictionary[format_value] = existing_value + 1

                                if USAGE_IDENTIFIER in trace_line:
                                    logger.debug(f'Found usage on line: {trace_line}')

                                    usage_start = trace_line.find(USAGE_IDENTIFIER) + USAGE_IDENTIFIER_LENGTH
                                    usage_value = trace_line[usage_start:trace_line.find(API_ENTRY_VALUE_DELIMITER,
                                                                                         usage_start)].strip()

                                    # at times there can be a single usage flag, ending in '},'
                                    usage_value = usage_value.replace('}', '')

                                    if not USAGE_SKIP_IDENTIFIER_D3D10_11 in usage_value:
                                        existing_value = self.usage_dictionary.get(usage_value, 0)
                                        self.usage_dictionary[usage_value] = existing_value + 1

                                if BIND_FLAGS_IDENTIFIER in trace_line:
                                    logger.debug(f'Found bind flags on line: {trace_line}')

                                    if BIND_FLAGS_SKIP_IDENTIFIER not in trace_line:
                                        bind_flags_start = trace_line.find(BIND_FLAGS_IDENTIFIER) + BIND_FLAGS_IDENTIFIER_LENGTH
                                        bind_flags = trace_line[bind_flags_start:trace_line.find(API_ENTRY_VALUE_DELIMITER,
                                                                                                bind_flags_start)].strip()

                                        bind_flags = bind_flags.split(BIND_FLAGS_SPLIT_DELIMITER)

                                        for bind_flag in bind_flags:
                                            bind_flag_stripped = bind_flag.strip()
                                            existing_value = self.bind_flag_dictionary.get(bind_flag_stripped, 0)
                                            self.bind_flag_dictionary[bind_flag_stripped] = existing_value + 1

                    else:
                        # these will usually be (numbered) memcpy lines
                        logger.debug(f'Skipped parsing of numbered line: {trace_line}')

                    if trace_call_counter > 0 and trace_call_counter % TRACE_LOGGING_CHUNK_CALLS == 0:
                        logger.info(f'Proccessed {trace_call_counter} apitrace calls...')

                self.process_queue.task_done()

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
                raise SystemExit(7)

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
    optional.add_argument('-o', '--output', help='path and filename of the JSON export')
    optional.add_argument('-n', '--name', help='specify a name for the apitraced application, using double quotes')
    optional.add_argument('-l', '--link', help='specify a web link for the application')
    optional.add_argument('-s', '--skip', help='specify apis to skip, e.g.: d3d9, d3d11')
    optional.add_argument('-d', '--dump', help='dumps the shader binaries included in an apitrace', action='store_true')
    optional.add_argument('-a', '--apitrace', help='path to the apitrace executable')
    optional.add_argument('-w', '--wine', help='use wine to launch the apitrace executable', action='store_true')

    args = parser.parse_args()

    tracestats = TraceStats(args.input, args.output, args.name, args.link, args.skip, args.dump, args.apitrace, args.wine)
    if not args.join:
        tracestats.process_traces()
    else:
        tracestats.join_json()

