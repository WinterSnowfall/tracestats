const MAX_FILE_SIZE_IN_BYTES = 16777216; // 16 MB

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
    url.searchParams.delete('search');
    window.history.replaceState({}, document.title, url);
}

function getURLSearchParameter() {
    const url = new URL(window.location.href);
    return url.searchParams.get('search');
}

$(document).on('click', '#toggle-filter-selection', function() {
    $.ajax({
        url: '/tracestats/filter-selection/',
        method: 'POST',
        headers: {
            'X-CSRFToken': getCookie('csrftoken')
        },
        success: function(response) {
            if (response.content) {
                $('#search-results').attr('class', 'no-margin');
                $('#search-results').html('');
                $('#notification-area').attr('class', 'notification-none');
                $('#notification-area').html('');
                $('#titles-list-area').html('');
                $('#stats-area').html('');
                $('#file-upload-area').html('');
                $('#toggle-titles-list').attr('class', 'search-button');
                $('#toggle-stats').attr('class', 'search-button');
                $('#toggle-file-upload').attr('class', 'search-button');
                $('#filter-selection-area').html(response.content);
                $('#toggle-filter-selection').attr('class', 'search-button-negative');
            } else {
                $('#search-results').attr('class', 'no-margin');
                $('#search-results').html('');
                $('#notification-area').attr('class', 'notification-none');
                $('#notification-area').html('');
                $('#filter-selection-area').html('');
                $('#toggle-filter-selection').attr('class', 'search-button');
            }
        }
    });
});

$(document).on('click', '#toggle-titles-list', function() {
    $.ajax({
        url: '/tracestats/titles-list/',
        method: 'POST',
        headers: {
            'X-CSRFToken': getCookie('csrftoken')
        },
        success: function(response) {
            if (response.content) {
                $('#search-results').attr('class', 'no-margin');
                $('#search-results').html('');
                $('#notification-area').attr('class', 'notification-none');
                $('#notification-area').html('');
                $('#filter-selection-area').html('');
                $('#stats-area').html('');
                $('#file-upload-area').html('');
                $('#toggle-filter-selection').attr('class', 'search-button');
                $('#toggle-stats').attr('class', 'search-button');
                $('#toggle-file-upload').attr('class', 'search-button');
                $('#titles-list-area').html(response.content);
                $('#toggle-titles-list').attr('class', 'search-button-negative');
            } else {
                $('#search-results').attr('class', 'no-margin');
                $('#search-results').html('');
                $('#notification-area').attr('class', 'notification-none');
                $('#notification-area').html('');
                $('#titles-list-area').html('');
                $('#toggle-titles-list').attr('class', 'search-button');
            }
        }
    });
});

$(document).on('click', '#toggle-stats', function() {
    $.ajax({
        url: '/tracestats/api-stats/',
        method: 'POST',
        headers: {
            'X-CSRFToken': getCookie('csrftoken')
        },
        success: function(response) {
            if (response.content) {
                $('#search-results').attr('class', 'no-margin');
                $('#search-results').html('');
                $('#notification-area').attr('class', 'notification-none');
                $('#notification-area').html('');
                $('#filter-selection-area').html('');
                $('#titles-list-area').html('');
                $('#file-upload-area').html('');
                $('#toggle-filter-selection').attr('class', 'search-button');
                $('#toggle-titles-list').attr('class', 'search-button');
                $('#toggle-file-upload').attr('class', 'search-button');
                $('#stats-area').html(response.content);
                $('#toggle-stats').attr('class', 'search-button-negative');

                const apiFilter = getCookie('apiFamilyFilter');

                let statsLabels = [];
                let statsColors = [];
                let statsData = [];

                if (apiFilter !== 'Glide') {
                    // D3D3
                    statsLabels.push('D3D3');
                    statsColors.push('#9C78AA');
                    statsData.push(response.api_stats['d3d3']);
                    // D3D5
                    statsLabels.push('D3D5');
                    statsColors.push('#A3A624');
                    statsData.push(response.api_stats['d3d5']);
                    // D3D6
                    statsLabels.push('D3D6');
                    statsColors.push('#D2B48C');
                    statsData.push(response.api_stats['d3d6']);
                    // D3D7
                    statsLabels.push('D3D7');
                    statsColors.push('#9C27B0');
                    statsData.push(response.api_stats['d3d7']);
                    // D3D8
                    statsLabels.push('D3D8');
                    statsColors.push('#F57C23');
                    statsData.push(response.api_stats['d3d8']);
                    // D3D9
                    statsLabels.push('D3D9');
                    statsColors.push('#FFEA00');
                    statsData.push(response.api_stats['d3d9']);
                    // D3D9Ex
                    statsLabels.push('D3D9Ex');
                    statsColors.push('#33CC33');
                    statsData.push(response.api_stats['d3d9ex']);
                    // D3D10
                    statsLabels.push('D3D10');
                    statsColors.push('#FF3D00');
                    statsData.push(response.api_stats['d3d10']);
                    // D3D11
                    statsLabels.push('D3D11');
                    statsColors.push('#36B4E1');
                    statsData.push(response.api_stats['d3d11']);
                }
                if (apiFilter !== 'Direct3D') {
                    // Glide1x
                    statsLabels.push('Glide1x');
                    statsColors.push('#BFBFBF');
                    statsData.push(response.api_stats['glide1x']);
                    // Glide2x
                    statsLabels.push('Glide2x');
                    statsColors.push('#808080');
                    statsData.push(response.api_stats['glide2x']);
                    // Glide3x
                    statsLabels.push('Glide3x');
                    statsColors.push('#404040');
                    statsData.push(response.api_stats['glide3x']);
                }

                new Chart($('#apiStatsPieChart')[0].getContext('2d'), {
                    type: 'pie',
                    data: {
                        labels: statsLabels,
                        datasets: [{
                            label: 'apitraces',
                            data: statsData,
                            backgroundColor: statsColors
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
                $('#search-results').attr('class', 'no-margin');
                $('#search-results').html('');
                $('#notification-area').attr('class', 'notification-none');
                $('#notification-area').html('');
                $('#stats-area').html('');
                $('#toggle-stats').attr('class', 'search-button');
            }
        }
    });
});

$(document).on('click', '#toggle-file-upload', function() {
    $.ajax({
        url: '/tracestats/file-upload/',
        method: 'POST',
        headers: {
            'X-CSRFToken': getCookie('csrftoken')
        },
        success: function(response) {
            if (response.content) {
                $('#search-results').attr('class', 'no-margin');
                $('#search-results').html('');
                $('#notification-area').attr('class', 'notification-none');
                $('#notification-area').html('');
                $('#filter-selection-area').html('');
                $('#titles-list-area').html('');
                $('#stats-area').html('');
                $('#toggle-filter-selection').attr('class', 'search-button');
                $('#toggle-titles-list').attr('class', 'search-button');
                $('#toggle-stats').attr('class', 'search-button');
                $('#file-upload-area').html(response.content);
                $('#toggle-file-upload').attr('class', 'search-button-negative');
            } else {
                $('#search-results').attr('class', 'no-margin');
                $('#search-results').html('');
                $('#notification-area').attr('class', 'notification-none');
                $('#notification-area').html('');
                $('#file-upload-area').html('');
                $('#toggle-file-upload').attr('class', 'search-button');
            }
        }
    });
});

$(document).on('click', '#filter-button', function() {
    $('#filter-selection-form').append(
        $('<input>').attr('type', 'hidden')
                    .attr('name', 'csrfmiddlewaretoken')
                    .val(getCookie('csrftoken'))
    );
    $('#filter-selection-form').append(
        $('<input>').attr('type', 'hidden')
                    .attr('name', 'search_input')
                    .val(getURLSearchParameter())
    );
    $('#filter-selection-form').submit();
});

$(document).on('click', '#upload-button', function() {
    const fileInput = $('.file-input');

    if (fileInput.length > 0) {
        const file = fileInput[0].files[0];

        if (file && file.size <= MAX_FILE_SIZE_IN_BYTES) {
            removeURLSearchParameter()
            $('#file-upload-form').append(
                $('<input>').attr('type', 'hidden')
                            .attr('name', 'csrfmiddlewaretoken')
                            .val(getCookie('csrftoken'))
            );
            $('#file-upload-form').submit();
        } else if (file && file.size > MAX_FILE_SIZE_IN_BYTES) {
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
    $('#search-results').attr('class', 'no-margin');
    $('#search-results').html('');
    $('#id_search_input').attr('value', '');
    $('#notification-area').attr('class', 'notification-none');
    $('#notification-area').html('');
});

$(document).on('click', '#reset-upload-form', function() {
    $('#upload-notification-area').attr('class', 'notification-none');
    $('#upload-notification-area').html('');
});

$(document).on('click', '#sort-alphabetically', function() {
    $.ajax({
        url: '/tracestats/titles-list/',
        method: 'POST',
        headers: {
            'X-CSRFToken': getCookie('csrftoken')
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
    $.ajax({
        url: '/tracestats/titles-list/',
        method: 'POST',
        headers: {
            'X-CSRFToken': getCookie('csrftoken')
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
    $.ajax({
        url: '/tracestats/titles-list/',
        method: 'POST',
        headers: {
            'X-CSRFToken': getCookie('csrftoken')
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
