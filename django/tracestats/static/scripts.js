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

function removeURLSearchParameter() {
    const url = new URL(window.location.href);
    url.searchParams.delete("search");
    window.history.replaceState({}, document.title, url);
}

$(document).ready(function() {
    if ($('.results-row').length > 0) {
        $('#search-results').show();
    } else {
        $('#search-results').hide();
    }
});

$(document).on('click', '#toggle-titles-list', function() {
    const csrftoken = getCookie('csrftoken');

    $.ajax({
        url: '/tracestats/titles-list/',
        method: 'POST',
        headers: {
            'X-CSRFToken': csrftoken
        },
        success: function(response) {
            if (response.content) {
                $('#search-results').hide();
                $('#notification-area').attr('class', 'notification-none');
                $('#notification-area').html('');
                $('#stats-area').html('');
                $('#file-upload-area').html('');
                $('#toggle-stats').attr('class', 'search-button');
                $('#toggle-file-upload').attr('class', 'search-button');
                $('#titles-list-area').html(response.content);
                $('#toggle-titles-list').attr('class', 'search-button-negative');
            } else {
                $('#search-results').hide();
                $('#notification-area').attr('class', 'notification-none');
                $('#notification-area').html('');
                $('#titles-list-area').html('');
                $('#toggle-titles-list').attr('class', 'search-button');
            }
        }
    });
});

$(document).on('click', '#toggle-stats', function() {
    removeURLSearchParameter();
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
                $('#notification-area').attr('class', 'notification-none');
                $('#notification-area').html('');
                $('#titles-list-area').html('');
                $('#file-upload-area').html('');
                $('#toggle-titles-list').attr('class', 'search-button');
                $('#toggle-file-upload').attr('class', 'search-button');
                $('#stats-area').html(response.content);
                $('#toggle-stats').attr('class', 'search-button-negative');

                const backgroundColors = [
                    '#9C27B0', // Vibrant Purple
                    '#F57C23', // Light Orange
                    '#FFEA00', // Bright Yellow
                    '#33CC33', // Dark Green
                    '#FF3D00', // Dark Orange
                    '#36B4E1', // Light Blue
                ];

                const ctx = $('#apiStatsPieChart')[0].getContext('2d');
                const myPieChart = new Chart(ctx, {
                    type: 'pie',
                    data: {
                        labels: ['D3D7', 'D3D8', 'D3D9', 'D3D9Ex', 'D3D10', 'D3D11'],
                        datasets: [{
                            label: 'apitraces',
                            data: [response.api_stats['d3d7'],
                                   response.api_stats['d3d8'],
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
                            tooltip: {
                                titleFont: {
                                    family: 'Lucida Console',
                                    size: 12
                                },
                                bodyFont: {
                                    family: 'Lucida Console',
                                    size: 12
                                }
                            },
                            legend: {
                                display: true,
                                position: 'right',
                                labels: {
                                    font: {
                                        family: 'Lucida Console',
                                        size: 12
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
                $('#notification-area').attr('class', 'notification-none');
                $('#notification-area').html('');
                $('#stats-area').html('');
                $('#toggle-stats').attr('class', 'search-button');
            }
        }
    });
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
                $('#notification-area').attr('class', 'notification-none');
                $('#notification-area').html('');
                $('#titles-list-area').html('');
                $('#stats-area').html('');
                $('#toggle-titles-list').attr('class', 'search-button');
                $('#toggle-stats').attr('class', 'search-button');
                $('#file-upload-area').html(response.content);
                $('#toggle-file-upload').attr('class', 'search-button-negative');
            } else {
                $('#search-results').hide();
                $('#notification-area').attr('class', 'notification-none');
                $('#notification-area').html('');
                $('#file-upload-area').html('');
                $('#toggle-file-upload').attr('class', 'search-button');
            }
        }
    });
});

$(document).on('click', '#upload-button', function() {
    removeURLSearchParameter();
    const fileInput = $('.file-input');

    if (fileInput.length > 0) {
        const file = fileInput[0].files[0];
        const maxSizeInBytes = 16777216; // 16 MB

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
                $('#upload-notification-area').html('Selected file size exceeds the 16 MB limit. Pick something else.');
            } else {
                $('#upload-notification-area').attr('class', 'notification-none');
                $('#upload-notification-area').html('');
            }
        } else {
            $('#upload-notification-area').attr('class', 'notification-none');
            $('#upload-notification-area').html('');
        }
    }
});

$(document).on('click', '#reset-search-form', function() {
    removeURLSearchParameter()
    $('#search-results').hide();
    $('#id_search_input').attr('value', '');
    $('#notification-area').attr('class', 'notification-none');
    $('#notification-area').html('');
});

$(document).on('click', '#reset-upload-form', function() {
    $('#upload-notification-area').attr('class', 'notification-none');
    $('#upload-notification-area').html('');
});

$(document).on('click', '#sort-alphabetically', function() {
    const csrftoken = getCookie('csrftoken');

    $.ajax({
        url: '/tracestats/titles-list/',
        method: 'POST',
        headers: {
            'X-CSRFToken': csrftoken
        },
        data: {
            sort: 0
        },
        success: function(response) {
            if (response.content) {
                $('#titles-list-area').html(response.content);
                $('#sort-alphabetically').attr('class', 'search-button-negative');
                $('#sort-api').attr('class', 'search-button');
                $('#sort-binary-name').attr('class', 'search-button');
            }
        }
    });
});

$(document).on('click', '#sort-api', function() {
    const csrftoken = getCookie('csrftoken');

    $.ajax({
        url: '/tracestats/titles-list/',
        method: 'POST',
        headers: {
            'X-CSRFToken': csrftoken
        },
        data: {
            sort: 1
        },
        success: function(response) {
            if (response.content) {
                $('#titles-list-area').html(response.content);
                $('#sort-alphabetically').attr('class', 'search-button');
                $('#sort-api').attr('class', 'search-button-negative');
                $('#sort-binary-name').attr('class', 'search-button');
            }
        }
    });
});

$(document).on('click', '#sort-binary-name', function() {
    const csrftoken = getCookie('csrftoken');

    $.ajax({
        url: '/tracestats/titles-list/',
        method: 'POST',
        headers: {
            'X-CSRFToken': csrftoken
        },
        data: {
            sort: 2
        },
        success: function(response) {
            if (response.content) {
                $('#titles-list-area').html(response.content);
                $('#sort-alphabetically').attr('class', 'search-button');
                $('#sort-api').attr('class', 'search-button');
                $('#sort-binary-name').attr('class', 'search-button-negative');
            }
        }
    });
});

