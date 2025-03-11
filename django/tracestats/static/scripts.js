$(document).ready(function() {
    if ($('.results-row').length > 0) {
        $('#search-results').show();
    } else {
        $('#search-results').hide();
    }

    $('#toggle-file-upload').click(function() {
        $.ajax({
            url: '/tracestats/file-upload/',
            method: 'GET',
            success: function(data) {
                if (data.content) {
                    $('#search-results').hide();
                    $('#notification-area').attr('class', 'notification-info');
                    $('#notification-area').html('');
                    $('#file-upload-area').html(data.content);
                    $('#toggle-file-upload').attr('class', 'search-button-negative');
                } else {
                    $('#search-results').hide();
                    $('#notification-area').attr('class', 'notification-info');
                    $('#notification-area').html('');
                    $('#file-upload').remove();
                    $('#toggle-file-upload').attr('class', 'search-button');
                }
            }
        })
    });
});

$(document).on('click', '#reset-search-form', function() {
    $('#search-results').hide();
    $('#id_search_input').attr('value', '');
    $('#notification-area').attr('class', 'notification-info');
    $('#notification-area').html('');
});

