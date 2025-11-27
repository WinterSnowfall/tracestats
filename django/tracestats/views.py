import json
import re
import logging

from urllib.parse import quote, unquote
from django.shortcuts import render, redirect
from django.template import loader
from django.http import JsonResponse
from django.template.context_processors import csrf
from django.utils.timezone import now
from . import forms
from . import models

logger = logging.getLogger('tracestats')

#constants
JSON_BASE_KEY = 'tracestats'
API_VALUES_ENCODE = {'D3D7'  : 1,
                     'D3D8'  : 2,
                     'D3D9'  : 3,
                     'D3D9Ex': 4,
                     'D3D10' : 5,
                     'D3D11' : 6}
API_VALUES_DECODE = {1: 'D3D7',
                     2: 'D3D8',
                     3: 'D3D9',
                     4: 'D3D9Ex',
                     5: 'D3D10',
                     6: 'D3D11'}
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
TRACE_API_OVERRIDES = {'wargame_'   : 'D3D9Ex', # Ignore queries done on a plain D3D9 interface, as it's not used for rendering
                       'xrEngine___': 'D3D10',  # Creates a D3D11 device first, but renders using D3D10
                       'RebelGalaxy': 'D3D11'}  # Creates a D3D10 device first, but renders using D3D11
STATS_TYPE = {'api_calls': 1,
              'vendor_hack_checks': 2,
              'device_types': 3,
              'behavior_flags': 4,
              'present_parameters': 5,
              'present_parameter_flags': 6,
              'render_states': 7,
              'query_types': 8,
              'lock_flags': 9,
              'shader_versions': 10,
              'usage': 11,
              'formats': 12,
              'vendor_hacks': 13,
              'pools': 14,
              'device_flags': 15,
              'swapchain_parameters': 16,
              'swapchain_buffer_usage': 17,
              'swapchain_flags': 18,
              'feature_levels': 19,
              'rastizer_states': 20,
              'blend_states': 21,
              'bind_flags': 22,
              'cooperative_level_flags': 23,
              'surface_caps': 24}
SEARCH_RESULTS_LIMIT = 999

def tracestats(request):
  request.session['titles_list_visible'] = False
  request.session['api_stats_visible'] = False
  request.session['file_upload_visible'] = False
  request.session.modified = True
  search_form = None
  search_results = None
  context = {}
  context['notification_type'] = 'notification-none'

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
                logger.debug(f'Application name is: {entry_application_name}')
                entry_binary_name = entry.get('binary_name')
                logger.debug(f'Binary name is: {entry_binary_name}')
                # use the binary name for the application name, if unspecified
                if entry_application_name is None:
                  entry_application_name = entry_binary_name
                entry_application_link = entry.get('link', None)

                entry_call_stats = entry.get('api_calls', {})
                # determine the API based on the entrypoint call
                entry_api = None
                entry_api_override = TRACE_API_OVERRIDES.get(entry_binary_name, None)
                if entry_api_override is not None:
                  entry_api = entry_api_override
                else:
                  for key, value in API_ENTRY_CALLS.items():
                    if key in entry_call_stats.keys():
                      entry_api = value
                      logger.debug(f'Found an entry call for: {entry_api}')
                      break
                logger.debug(f'API is: {entry_api}')
                if entry_api is None:
                  raise Exception('Invalid JSON structure')
                # convert API name to numeric value
                else:
                  entry_api = API_VALUES_ENCODE.get(entry_api)

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

                for stat_type in STATS_TYPE.keys():
                  entry_stats_values = entry.get(stat_type, {})
                  stats = []
                  for key, value in entry_stats_values.items():
                    stats.append(models.Stats(trace=trace,
                                              stat_type=STATS_TYPE[stat_type],
                                              stat_name=key,
                                              stat_count=value))
                  if len(stats) > 0:
                    models.Stats.objects.bulk_create(stats)

              context = {'notification_message': 'All good. You\'ve cossed the Bridge of Death.',
                         'notification_type': 'notification-success'}
            else:
              context = {'notification_message': 'The JSON structure is incorrect. Just use whatever tracestats generates, ok?',
                         'notification_type': 'notification-error'}

          except UnicodeDecodeError:
            context = {'notification_message': 'That\'s not even a text file. Try hader next time, won\'t you?',
                       'notification_type': 'notification-error'}
          except json.JSONDecodeError:
            context = {'notification_message': 'That is most certainly not a JSON. Think you\'re pretty funny, don\'t ya\'?',
                       'notification_type': 'notification-error'}
          except Exception as e:
            logger.error('Encountered exception: ', exc_info=e)
            context = {'notification_message': 'The JSON structure is incorrect. Just use whatever tracestats generates, ok?',
                       'notification_type': 'notification-error'}
        else:
          context = {'notification_message': 'Wrong answer. You\'ve been cast into the Gorge of Eternal Peril!',
                     'notification_type': 'notification-error'}
      else:
        context = {'notification_message': 'That file has upset the Rabbit of Caerbannog. Naughty naughty.',
                   'notification_type': 'notification-error'}

    elif 'search-form' in request.POST:
      search_form = forms.SearchForm(request.POST)
      if search_form.is_valid():
        search_input = request.POST['search_input'].strip()
        return redirect(f'{request.path}?search={quote(search_input)}')

    else:
      logger.error('What in the bloody blazes is this?')

  elif request.method == 'GET':
    search_input = request.GET.get('search', None)

    if search_input is not None:
      logger.info(f'Search input: {search_input}')

      if len(search_input) < 2:
        return redirect(f'{request.path}')

      search_input = unquote(search_input)
      search_form = forms.SearchForm(initial={'search_input': search_input})
      exact_search = False

      search_bang_split = search_input.rsplit(' ', 1)
      if len(search_bang_split) > 1 and search_bang_split[1] == '!':
        search_input = search_bang_split[0]
        exact_search = True

      # Note that all searches are case insensitive in SQLite
      if not exact_search:
        search_results = models.Stats.objects.filter(stat_name__icontains=search_input).order_by('stat_type',
                                                                                                 '-stat_count',
                                                                                                 'trace__name',
                                                                                                 'trace__api')[:SEARCH_RESULTS_LIMIT]
      else:
        search_results = models.Stats.objects.filter(stat_name__exact=search_input).order_by('stat_type',
                                                                                             '-stat_count',
                                                                                             'trace__name',
                                                                                             'trace__api')[:SEARCH_RESULTS_LIMIT]

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
                     'notification_type': 'notification-info'}
      else:
        # Highlight the searched text in the returned results
        for search_result in search_results:
          result_stat_name = search_result.stat_name

          highlighted_text = re.sub(re.escape(search_input),
                                    lambda match: f'<mark>{match.group(0)}</mark>',
                                    result_stat_name,
                                    flags=re.IGNORECASE)
          search_result.stat_name = highlighted_text

  context['traces_total'] = models.Trace.objects.count()

  if search_form is None:
    search_form = forms.SearchForm()
  template = loader.get_template('home.html')
  context['form'] = search_form
  context['api_values_decode'] = API_VALUES_DECODE
  context['search_results'] = search_results
  return render(request, 'home.html', context)

def generate_titles_list(request):
  if request.method != 'POST':
    return JsonResponse({'error': 'The Rabbit of Caerbannog pounces on you and you die!'}, status=403)
  else:
    try:
      sort_by = int(request.POST.get('sort'))
    except:
      sort_by = None

    if sort_by == 1:
      titles_list = models.Trace.objects.only('name', 'link', 'binary_name', 'api').order_by('api',
                                                                                             'name')
    elif sort_by == 2:
      titles_list = models.Trace.objects.only('name', 'link', 'binary_name', 'api').order_by('binary_name')
    # Catch-all for 0 or None
    else:
      titles_list = models.Trace.objects.only('name', 'link', 'binary_name', 'api').order_by('name',
                                                                                             'api')

    if sort_by is None:
      try:
        request.session['titles_list_visible'] = not request.session['titles_list_visible']
        request.session.modified = True
      except KeyError:
        request.session['titles_list_visible'] = True
        request.session.modified = True
    else:
      request.session['titles_list_visible'] = True

    if request.session['titles_list_visible']:
      context = {}
      context['titles_list'] = titles_list
      context['api_values_decode'] = API_VALUES_DECODE
      context.update(csrf(request))
      content = loader.render_to_string('titles_list.html', context)
    else:
      content = ""

    request.session['api_stats_visible'] = False
    request.session['file_upload_visible'] = False
    request.session.modified = True

    return JsonResponse({'content': content})

def generate_stats(request):
  if request.method != 'POST':
    return JsonResponse({'error': 'The Rabbit of Caerbannog pounces on you and you die!'}, status=403)
  else:
    api_stats = {}

    try:
      request.session['api_stats_visible'] = not request.session['api_stats_visible']
      request.session.modified = True
    except KeyError:
      request.session['api_stats_visible'] = True
      request.session.modified = True

    if request.session['api_stats_visible']:
      api_stats['d3d7']   = models.Trace.objects.filter(api=1).count()
      api_stats['d3d8']   = models.Trace.objects.filter(api=2).count()
      api_stats['d3d9']   = models.Trace.objects.filter(api=3).count()
      api_stats['d3d9ex'] = models.Trace.objects.filter(api=4).count()
      api_stats['d3d10']  = models.Trace.objects.filter(api=5).count()
      api_stats['d3d11']  = models.Trace.objects.filter(api=6).count()

      context = {}
      context.update(csrf(request))
      content = loader.render_to_string('api_stats.html', context)
    else:
      content = ""

    request.session['titles_list_visible'] = False
    request.session['file_upload_visible'] = False
    request.session.modified = True

    return JsonResponse({'content': content,
                         'api_stats': api_stats})

def generate_file_upload(request):
  if request.method != 'POST':
    return JsonResponse({'error': 'The Rabbit of Caerbannog pounces on you and you die!'}, status=403)
  else:
    try:
      request.session['file_upload_visible'] = not request.session['file_upload_visible']
      request.session.modified = True
    except KeyError:
      request.session['file_upload_visible'] = True
      request.session.modified = True

    if request.session['file_upload_visible']:
      file_upload_form = forms.FileUploadForm()
      context = {'file_upload_form': file_upload_form}
      context.update(csrf(request))
      content = loader.render_to_string('file_upload.html', context)
    else:
      content = ""

    request.session['titles_list_visible'] = False
    request.session['api_stats_visible'] = False
    request.session.modified = True

    return JsonResponse({'content': content})

