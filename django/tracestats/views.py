import json
import re
import logging

from django.shortcuts import render
from django.template import loader
from django.http import JsonResponse
from django.template.context_processors import csrf
from django.utils.timezone import now
from . import forms
from . import models

logger = logging.getLogger('tracestats')

#constants
JSON_BASE_KEY = 'tracestats'
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
STATS_TYPE = {'api_calls': 1,
              'device_types': 2,
              'behavior_flags': 3,
              'present_parameters': 4,
              'render_states': 5,
              'query_types': 6,
              'formats': 7,
              'pools': 8,
              'device_flags': 9,
              'feature_levels': 10,
              'rastizer_states': 11,
              'blend_states': 12,
              'usage': 13,
              'bind_flags': 14}
SEARCH_RESULTS_LIMIT = 500

def tracestats(request):
  request.session['content_visible'] = False
  request.session.modified = True
  search_form = None
  search_results = None
  context = {}

  if request.method == 'POST':
    if 'upload-form' in request.POST:
      form = forms.FileUploadForm(request.POST, request.FILES)
      if form.is_valid():
        upload_token = request.POST['authorization_token']
        #logger.debug(f'Auth_token: {upload_token}')

        try:
          token = models.Tokens.objects.get(token=upload_token)
        except models.Tokens.DoesNotExist:
          token = None

        if token is not None:
          uploaded_file = request.FILES['file_upload']
          logger.debug(f'Uploaded file name is: {uploaded_file.name}')

          try:
            # Read the content of the file
            file_content = uploaded_file.read().decode('utf-8')
            tracestats_data = json.loads(file_content).get(JSON_BASE_KEY)

            if tracestats_data is not None:
              for entry in tracestats_data:
                # create/update base trace db entry
                entry_application_name = entry.get('name')
                entry_binary_name = entry.get('binary_name')
                # use the binary name for the application name, if unspecified
                if entry_application_name is None:
                  entry_application_name = entry_binary_name
                entry_application_link = entry.get('link', None)

                # determine the API based on the entrypoint call
                entry_api = None
                entry_call_stats = entry.get('api_calls', {})
                for key, value in API_ENTRY_CALLS.items():
                  if key in entry_call_stats.keys():
                    entry_api = value
                    logger.debug(f'Found an entry call for: {entry_api}')
                    break
                if entry_api is None:
                  raise Exception('Invalid JSON structure')

                # determine the total API call count in the trace
                entry_api_calls_total = 0
                for value in entry_call_stats.values():
                  entry_api_calls_total = entry_api_calls_total + value
                # don't populate the db field to save some space if 0
                if entry_api_calls_total == 0:
                  entry_api_calls_total = None
                logger.debug(f'Total API call count is: {entry_api_calls_total}')

                entry_render_states = entry.get('render_states', {})
                # determine the total render state count in the trace
                entry_render_states_total = 0
                for value in entry_render_states.values():
                  entry_render_states_total = entry_render_states_total + value
                # don't populate the db field to save some space if 0
                if entry_render_states_total == 0:
                  entry_render_states_total = None
                logger.debug(f'Total render state count is: {entry_render_states_total}')

                entry_query_types = entry.get('query_types', {})
                # determine the total query types count in the trace
                entry_query_types_total = 0
                for value in entry_query_types.values():
                  entry_query_types_total = entry_query_types_total + value
                # don't populate the db field to save some space if 0
                if entry_query_types_total == 0:
                  entry_query_types_total = None
                logger.debug(f'Total query types count is: {entry_query_types_total}')

                try:
                  existing_trace = models.Trace.objects.get(name=entry_application_name, api=entry_api)
                except models.Trace.DoesNotExist:
                  existing_trace = None

                if existing_trace is None:
                  trace = models.Trace(name=entry_application_name,
                                       link=entry_application_link,
                                       binary_name=entry_binary_name,
                                       updated_by=token,
                                       api=entry_api,
                                       api_calls_total=entry_api_calls_total,
                                       render_states_total=entry_render_states_total,
                                       query_types_total=entry_query_types_total)
                  trace.save()
                else:
                  trace = existing_trace
                  # clear any existing stats if we are updating the trace
                  models.Stats.objects.filter(trace=trace).delete()
                  # update the new values in the trace entry
                  trace.link = entry_application_link
                  trace.binary_name = entry_binary_name
                  trace.updated_by = token
                  trace.updated_last = now()
                  trace.api = entry_api
                  trace.api_calls_total = entry_api_calls_total
                  trace.render_states_total = entry_render_states_total
                  trace.query_types_total = entry_query_types_total
                  trace.save()

                # create child stats entries for API calls
                stats = []
                for key, value in entry_call_stats.items():
                  stats.append(models.Stats(trace=trace,
                                            stat_type=STATS_TYPE['api_calls'],
                                            stat_name=key,
                                            stat_count=value))
                if len(stats) > 0:
                  models.Stats.objects.bulk_create(stats)

                # create child stats entries for device types
                entry_device_types = entry.get('device_types', {})
                stats = []
                for key, value in entry_device_types.items():
                  stats.append(models.Stats(trace=trace,
                                            stat_type=STATS_TYPE['device_types'],
                                            stat_name=key,
                                            stat_count=value))
                if len(stats) > 0:
                  models.Stats.objects.bulk_create(stats)

                # create child stats entries for behavior flags
                entry_behavior_flags = entry.get('behavior_flags', {})
                stats = []
                for key, value in entry_behavior_flags.items():
                  stats.append(models.Stats(trace=trace,
                                            stat_type=STATS_TYPE['behavior_flags'],
                                            stat_name=key,
                                            stat_count=value))
                if len(stats) > 0:
                  models.Stats.objects.bulk_create(stats)

                # create child stats entries for present parameters
                entry_present_parameters = entry.get('present_parameters', {})
                stats = []
                for key, value in entry_present_parameters.items():
                  stats.append(models.Stats(trace=trace,
                                            stat_type=STATS_TYPE['present_parameters'],
                                            stat_name=key,
                                            stat_count=value))
                if len(stats) > 0:
                  models.Stats.objects.bulk_create(stats)

                # create child stats entries for render states
                stats = []
                for key, value in entry_render_states.items():
                  stats.append(models.Stats(trace=trace,
                                            stat_type=STATS_TYPE['render_states'],
                                            stat_name=key,
                                            stat_count=value))
                if len(stats) > 0:
                  models.Stats.objects.bulk_create(stats)

                # create child stats entries for query types
                stats = []
                for key, value in entry_query_types.items():
                  stats.append(models.Stats(trace=trace,
                                            stat_type=STATS_TYPE['query_types'],
                                            stat_name=key,
                                            stat_count=value))
                if len(stats) > 0:
                  models.Stats.objects.bulk_create(stats)

                # create child stats entries for render formats
                entry_formats = entry.get('formats', {})
                stats = []
                for key, value in entry_formats.items():
                  stats.append(models.Stats(trace=trace,
                                            stat_type=STATS_TYPE['formats'],
                                            stat_name=key,
                                            stat_count=value))
                if len(stats) > 0:
                  models.Stats.objects.bulk_create(stats)

                # create child stats entries for pools
                entry_pools = entry.get('pools', {})
                stats = []
                for key, value in entry_pools.items():
                  stats.append(models.Stats(trace=trace,
                                            stat_type=STATS_TYPE['pools'],
                                            stat_name=key,
                                            stat_count=value))
                if len(stats) > 0:
                  models.Stats.objects.bulk_create(stats)

                # create child stats entries for device flags
                entry_device_flags = entry.get('device_flags', {})
                stats = []
                for key, value in entry_device_flags.items():
                  stats.append(models.Stats(trace=trace,
                                            stat_type=STATS_TYPE['device_flags'],
                                            stat_name=key,
                                            stat_count=value))
                if len(stats) > 0:
                  models.Stats.objects.bulk_create(stats)

                # create child stats entries for feature levels
                entry_feature_levels = entry.get('feature_levels', {})
                stats = []
                for key, value in entry_feature_levels.items():
                  stats.append(models.Stats(trace=trace,
                                            stat_type=STATS_TYPE['feature_levels'],
                                            stat_name=key,
                                            stat_count=value))
                if len(stats) > 0:
                  models.Stats.objects.bulk_create(stats)

                # create child stats entries for raster states
                entry_rastizer_states = entry.get('rastizer_states', {})
                stats = []
                for key, value in entry_rastizer_states.items():
                  stats.append(models.Stats(trace=trace,
                                            stat_type=STATS_TYPE['rastizer_states'],
                                            stat_name=key,
                                            stat_count=value))
                if len(stats) > 0:
                  models.Stats.objects.bulk_create(stats)

                # create child stats entries for blend states
                entry_blend_states = entry.get('blend_states', {})
                stats = []
                for key, value in entry_blend_states.items():
                  stats.append(models.Stats(trace=trace,
                                            stat_type=STATS_TYPE['blend_states'],
                                            stat_name=key,
                                            stat_count=value))
                if len(stats) > 0:
                  models.Stats.objects.bulk_create(stats)

                # create child stats entries for usage
                entry_usage = entry.get('usage', {})
                stats = []
                for key, value in entry_usage.items():
                  stats.append(models.Stats(trace=trace,
                                            stat_type=STATS_TYPE['usage'],
                                            stat_name=key,
                                            stat_count=value))
                if len(stats) > 0:
                  models.Stats.objects.bulk_create(stats)

                # create child stats entries for bind flags
                entry_bind_flags = entry.get('bind_flags', {})
                stats = []
                for key, value in entry_bind_flags.items():
                  stats.append(models.Stats(trace=trace,
                                            stat_type=STATS_TYPE['bind_flags'],
                                            stat_name=key,
                                            stat_count=value))
                if len(stats) > 0:
                  models.Stats.objects.bulk_create(stats)

              context = {'notification_message': 'All good. You\'ve cossed the Bridge of Death.',
                      'notification_type': 'info'}
            else:
              context = {'notification_message': 'The JSON structure is incorrect. Just use whatever tracestats generates, ok?',
                      'notification_type': 'error'}

          except UnicodeDecodeError:
            context = {'notification_message': 'That\'s not even a text file. Try hader next time, won\'t you?',
                      'notification_type': 'error'}
          except json.JSONDecodeError:
            context = {'notification_message': 'That is most certainly not a JSON. Think you\'re pretty funny, don\'t ya\'?',
                      'notification_type': 'error'}
          except:
            context = {'notification_message': 'The JSON structure is incorrect. Just use whatever tracestats generates, ok?',
                      'notification_type': 'error'}
        else:
          context = {'notification_message': 'Wrong answer. You\'ve been cast into the Gorge of Eternal Peril!',
                    'notification_type': 'error'}

    elif 'search-form' in request.POST:
      search_form = forms.SearchForm(request.POST)
      if search_form.is_valid():
        search_input = request.POST['search_input'].strip()
        logger.info(f'Search_Input: {search_input}')
        exact_search = False

        search_bang_split = search_input.rsplit(' ', 1)
        if len(search_bang_split) > 1 and search_bang_split[1] == '!':
          search_input = search_bang_split[0]
          exact_search = True

        # Note that all searches are case insensitive in SQLite
        if not exact_search:
          search_results = models.Stats.objects.filter(stat_name__icontains=search_input).order_by('stat_type',
                                                                                                   '-stat_count',
                                                                                                   'trace__name')[:SEARCH_RESULTS_LIMIT]
        else:
          search_results = models.Stats.objects.filter(stat_name__exact=search_input).order_by('stat_type',
                                                                                               '-stat_count',
                                                                                               'trace__name')[:SEARCH_RESULTS_LIMIT]

        if len(search_results) == 0:
          # If no objects are found, do a search based on application names
          if not exact_search:
            search_results = models.Stats.objects.filter(trace__name__icontains=search_input).order_by('trace__name',
                                                                                                       'trace__api',
                                                                                                       'stat_type',
                                                                                                       '-stat_count')[:SEARCH_RESULTS_LIMIT]
          else:
            search_results = models.Stats.objects.filter(trace__name__exact=search_input).order_by('trace__name',
                                                                                                   'trace__api',
                                                                                                   'stat_type',
                                                                                                   '-stat_count')[:SEARCH_RESULTS_LIMIT]

          if len(search_results) == 0:
            # If no results of any kind could be found, show a notification to that extent
            context = {'notification_message': 'I\'m afraid that particular shrubbery is nowhere to be found.',
                       'notification_type': 'highlight'}
        else:
          # Highlight the searched text in the returned results
          for search_result in search_results:
            result_stat_name = search_result.stat_name

            highlighted_text = re.sub(re.escape(search_input),
                                      lambda match: f'<mark>{match.group(0)}</mark>',
                                      result_stat_name,
                                      flags=re.IGNORECASE)
            search_result.stat_name = highlighted_text

    else:
      logger.error('What in the bloody blazes is this?')

  context['traces_total'] = models.Trace.objects.count()

  if search_form is None:
    search_form = forms.SearchForm()
  template = loader.get_template('home.html')
  context['form'] = search_form
  context['search_results'] = search_results
  return render(request, 'home.html', context)

def generate_file_upload(request):
  try:
    request.session['content_visible'] = not request.session['content_visible']
    request.session.modified = True
  except KeyError:
    request.session['content_visible'] = True
    request.session.modified = True

  if request.session['content_visible']:
      file_upload_form = forms.FileUploadForm()
      context = {'file_upload_form': file_upload_form}
      context.update(csrf(request))
      content = loader.render_to_string('file_upload.html', context)
  else:
      content = ""

  return JsonResponse({'content': content})

