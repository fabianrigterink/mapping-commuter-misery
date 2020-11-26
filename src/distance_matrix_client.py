import configparser
import json
import time
import urllib.error
import urllib.parse
import urllib.request

class DistanceMatrixClient:
    def __init__(self):
        config = configparser.ConfigParser()
        config.read('config.ini')
        assert 'DISTANCE_MATRIX_API_KEY' in config['DEFAULT'], 'Could not find key \'DISTANCE_MATRIX_API_KEY\' in config.ini. Exit.'
        API_KEY = config['DEFAULT']['DISTANCE_MATRIX_API_KEY']
        self.API_KEY = API_KEY
        print(self.API_KEY)

    DISTANCE_MATRIX_BASE_URL = 'https://maps.googleapis.com/maps/api/distancematrix/json'

    def get_distance(self, origins: list, destinations: list, mode: str, arrival_time=None, departure_time=None):

        assert len(origins) > 0
        assert len(destinations) > 0
        assert len(origins) * len(destinations) <= 100
        assert mode in ['driving', 'walking', 'bicycling', 'transit']
        assert arrival_time is not None or departure_time is not None

        # Join the parts of the URL together into one string.
        params = urllib.parse.urlencode({
            # Required parameters
            'origins'      : '|'.join(['{},{}'.format(lat, lng) for (lat, lng) in origins]),
            'destinations' : '|'.join(['{},{}'.format(lat, lng) for (lat, lng) in destinations]),
            'key'          : self.API_KEY,
            # Optional parameters
            'mode'         : mode
        })
        params_time = None
        if arrival_time is not None:
            params_time = urllib.parse.urlencode({'arrival_time': int(arrival_time)})
        elif departure_time is not None:
            params_time = urllib.parse.urlencode({'departure_time' : int(departure_time)})

        url = '{}?{}&{}'.format(self.DISTANCE_MATRIX_BASE_URL, params, params_time)

        current_delay = 0.1  # Set the initial retry delay to 100ms.
        max_delay = 5  # Set the maximum retry delay to 5 seconds.

        while True:
            try:
                # Get the API response.
                response = urllib.request.urlopen(url)
            except urllib.error.URLError:
                pass  # Fall through to the retry loop.
            else:
                # If we didn't get an IOError then parse the result.
                result = json.load(response)

                if result['status'] == 'OK':
                    return json.dumps(result)
                elif result['status'] != 'UNKNOWN_ERROR':
                    # Many API errors cannot be fixed by a retry, e.g. INVALID_REQUEST or
                    # ZERO_RESULTS. There is no point retrying these requests.
                    raise Exception(result['error_message'])

            if current_delay > max_delay:
                raise Exception('Too many retry attempts.')

            print('Waiting', current_delay, 'seconds before retrying.')

            time.sleep(current_delay)
            current_delay *= 2  # Increase the delay each time we retry.