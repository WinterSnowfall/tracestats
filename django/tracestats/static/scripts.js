function getCookie(name) {
    let cookieValue = null;

    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }

    return cookieValue;
}

$(document).ready(function() {
    if ($('.results-row').length > 0) {
        $('#search-results').show();
    } else {
        $('#search-results').hide();
    }
});

$(document).on('click', '#toggle-file-upload', function() {
    const csrftoken = getCookie('csrftoken');

    $.ajax({
        url: '/tracestats/file-upload/',
        method: 'POST',
        headers: {
            'X-CSRFToken': csrftoken
        },
        success: function(response) {
            if (response.content) {
                $('#search-results').hide();
                $('#notification-area').attr('class', 'notification-info');
                $('#notification-area').html('');
                $('#stats-area').html('');
                $('#toggle-stats').attr('class', 'search-button');
                $('#file-upload-area').html(response.content);
                $('#toggle-file-upload').attr('class', 'search-button-negative');
            } else {
                $('#search-results').hide();
                $('#notification-area').attr('class', 'notification-info');
                $('#notification-area').html('');
                $('#file-upload-area').html('');
                $('#toggle-file-upload').attr('class', 'search-button');
            }
        }
    });
});

$(document).on('click', '#toggle-stats', function() {
    const csrftoken = getCookie('csrftoken');

    $.ajax({
        url: '/tracestats/api-stats/',
        method: 'POST',
        headers: {
            'X-CSRFToken': csrftoken
        },
        success: function(response) {
            if (response.content) {
                $('#search-results').hide();
                $('#notification-area').attr('class', 'notification-info');
                $('#notification-area').html('');
                $('#file-upload-area').html('');
                $('#toggle-file-upload').attr('class', 'search-button');
                $('#stats-area').html(response.content);
                $('#toggle-stats').attr('class', 'search-button-negative');

                const backgroundColors = [
                    '#FF5722', // Deep Orange
                    '#FFC107', // Golden Yellow
                    '#FF3D00', // Dark Orange
                    '#FFEA00', // Bright Yellow
                    '#FF9800'  // Light Orange
                ];

                const ctx = $('#apiStatsPieChart')[0].getContext('2d');
                const myPieChart = new Chart(ctx, {
                    type: 'pie',
                    data: {
                        labels: ['D3D8', 'D3D9', 'D3D9Ex', 'D3D10', 'D3D11'],
                        datasets: [{
                            label: 'apitraces',
                            data: [response.api_stats['d3d8'],
                                   response.api_stats['d3d9'],
                                   response.api_stats['d3d9ex'],
                                   response.api_stats['d3d10'],
                                   response.api_stats['d3d11']],
                            backgroundColor: backgroundColors
                        }]
                    },
                    options: {
                        responsive: false,
                        plugins: {
                            legend: {
                                display: true,
                                position: 'right',
                                labels: {
                                    font: {
                                        family: 'Lucida Console'
                                    },
                                    boxWidth: 20,
                                    padding: 15,
                                    color: 'white'
                                }
                            },
                            title: {
                                display: false
                            }
                        }
                    }
                });
            } else {
                $('#search-results').hide();
                $('#notification-area').attr('class', 'notification-info');
                $('#notification-area').html('');
                $('#stats-area').html('');
                $('#toggle-stats').attr('class', 'search-button');
            }
        }
    });
});

$(document).on('click', '#upload-button', function() {
    const fileInput = $('.file-input');

    if (fileInput.length > 0) {
        const file = fileInput[0].files[0];
        const maxSizeInBytes = 4194304; // 4 MB

        if (file && file.size <= maxSizeInBytes) {
            const csrfInput = $('<input>')
                                .attr('type', 'hidden')
                                .attr('name', 'csrfmiddlewaretoken')
                                .val(getCookie('csrftoken'));
            $('#file-upload-form').append(csrfInput);
            $('#file-upload-form').submit();
        } else if (file && file.size > maxSizeInBytes) {
            if($('.password-input').val()) {
                $('#file-upload-form')[0].reset();
                $('#upload-notification-area').attr('class', 'notification-error');
                $('#upload-notification-area').html('Selected file size exceeds the 4 MB limit. Pick something else.');
            } else {
                $('#upload-notification-area').attr('class', 'notification-info');
                $('#upload-notification-area').html('');
            }
        } else {
            $('#upload-notification-area').attr('class', 'notification-info');
            $('#upload-notification-area').html('');
        }
    }
});

$(document).on('click', '#reset-search-form', function() {
    $('#search-results').hide();
    $('#id_search_input').attr('value', '');
    $('#notification-area').attr('class', 'notification-info');
    $('#notification-area').html('');
});

$(document).on('click', '#reset-upload-form', function() {
    $('#upload-notification-area').attr('class', 'notification-info');
    $('#upload-notification-area').html('');
});

