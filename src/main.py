import datetime
from distance_matrix_client import DistanceMatrixClient
import itertools
import json
import math
import pandas as pd
from pyproj import Transformer
import pytz
import requests
from shapely.geometry import shape, Point, Polygon


def save_polygon(relation_id: int, polygon_file: str):
    url = 'http://polygons.openstreetmap.fr/get_geojson.py?id={}'.format(relation_id)
    r = requests.get(url)
    assert r.status_code == 200
    f = open(polygon_file, 'w', encoding='utf-8')
    f.write(r.text)
    f.close()


def get_sw_ne(polygon_file: str):
    with open(polygon_file, encoding='utf-8') as f:
        data = json.load(f)

    lats = []
    lngs = []

    assert 'geometries' in data.keys()
    geometries = data.get('geometries')
    for geometry in geometries:
        assert 'coordinates' in geometry
        coordinates = geometry.get('coordinates')
        for coordinate in coordinates:
            assert len(coordinate) > 0
            lats += [latlng[1] for latlng in coordinate[0]]
            lngs += [latlng[0] for latlng in coordinate[0]]
    
    return (min(lats), min(lngs)), (max(lats), max(lngs))


def get_grid_points(sw: tuple, ne: tuple, mesh_size: int, polygon_file: str):
    transformer_l2m = Transformer.from_crs(4326, 3857, always_xy=True)
    transformer_m2l = Transformer.from_crs(3857, 4326, always_xy=True)

    # pyproj and shapely assume (lng, lat) format, so transform from (lat, lng) to (lng, lat)
    sw_ne_l = [(sw[1], sw[0]), (ne[1], ne[0])]
    sw_ne_m = list(transformer_l2m.itransform(sw_ne_l))

    x_m = list(range(math.floor(sw_ne_m[0][0]), math.ceil(sw_ne_m[1][0]), mesh_size))
    y_m = list(range(math.floor(sw_ne_m[0][1]), math.ceil(sw_ne_m[1][1]), mesh_size))

    xy_m = list(itertools.product(x_m, y_m))
    xy_l = list(transformer_m2l.itransform(xy_m))

    with open(polygon_file, encoding='utf-8') as f:
        data = json.load(f)

    points = []

    for p in xy_l:
        point = Point(p[0], p[1])
        assert 'geometries' in data.keys()
        for geometry in data['geometries']:
            polygon = shape(geometry)
            if polygon.contains(point):
                # We assume (lat, lng) format, so transform from (lng, lat) to (lat, lng)
                points.append((p[1], p[0]))

    return points


def save_points(points: list, points_file: str):
    df = pd.DataFrame(points, columns=['lat', 'lng'])
    df.to_csv(points_file, index=False)


def save_distances(distances: str, distances_file: str):
    f = open(distances_file, 'w', encoding='utf-8')
    f.write(distances)
    f.close()


"""
Main parameters
"""

# Top 10 most populated cities in the U.S.
cities = {
    'New York City' : { 'relation_id':  175905, 'city_hall_lat_lng': (40.7128,  -74.0060), 'timezone':  'US/Eastern' },
    #'Los Angeles'   : { 'relation_id':  207359, 'city_hall_lat_lng': (34.0522, -118.2437), 'timezone':  'US/Pacific' },
    #'Chicago'       : { 'relation_id':  122604, 'city_hall_lat_lng': (41.8781,  -87.6298), 'timezone':  'US/Central' },
    #'Houston'       : { 'relation_id': 2688911, 'city_hall_lat_lng': (29.7604,  -95.3698), 'timezone':  'US/Central' },
    #'Phoenix'       : { 'relation_id':  111257, 'city_hall_lat_lng': (33.4484, -112.0740), 'timezone': 'US/Mountain' },
    #'Philadelphia'  : { 'relation_id':  188022, 'city_hall_lat_lng': (39.9526,  -75.1652), 'timezone':  'US/Eastern' },
    #'San Antonio'   : { 'relation_id':  253556, 'city_hall_lat_lng': (29.4241,  -98.4936), 'timezone':  'US/Central' },
    #'San Diego'     : { 'relation_id':  253832, 'city_hall_lat_lng': (32.7157, -117.1611), 'timezone':  'US/Pacific' },
    #'Dallas'        : { 'relation_id': 6571629, 'city_hall_lat_lng': (32.7767,  -96.7970), 'timezone':  'US/Central' },
    #'San Jose'      : { 'relation_id':  112143, 'city_hall_lat_lng': (37.3382, -121.8863), 'timezone':  'US/Pacific' },
}

modes      = ['driving', 'walking', 'bicycling', 'transit']
directions = ['arrival', 'departure']
# | Mesh size | Distance Matrix calls |
# |-----------|-----------------------|
# |      1000 |                 1,280 |
# |       500 |                 5,008 |
# |       100 |               124,048 |
mesh_size  = 500 # The grid's mesh size in meters

# Let's commute on Wednesday, Dec 2, with the work hours 9-5
workday     = datetime.date(2020, 12, 2)
workday_tic = datetime.time(9)
workday_toc = datetime.time(17)

distance_matrix_client = DistanceMatrixClient()

"""
/Main parameters
"""


def save_inputs():
    for city in cities.keys():
        print('City = {}'.format(city))

        city_slug    = city.lower().replace(' ', '-')
        polygon_file = 'data/polygon-{}.json'.format(city_slug)
        points_file  = 'data/points-{}.csv'.format(city_slug)
        
        # Save the city's polygon as a json file using http://polygons.openstreetmap.fr/get_geojson.py
        save_polygon(relation_id=cities.get(city).get('relation_id'), polygon_file=polygon_file)
        # Get the Southwesternmost and Northeastern most points
        sw, ne = get_sw_ne(polygon_file=polygon_file)
        # Get grid points within the polygon using a mesh with size mesh_size
        points = get_grid_points(sw=sw, ne=ne, mesh_size=mesh_size, polygon_file=polygon_file)
        # Save the city's grid points as a CSV file
        save_points(points=points, points_file=points_file)

        # Get distances using the Google Distance Matrix API
        for mode in modes:
            print('\tMode = {}'.format(mode))

            df = pd.read_csv(points_file)

            for i in list(range(0, len(df), 100)):
                i_end = None
                if i + 100 <= len(df):
                    i_end = i + 100
                else:
                    i_end = len(df)
                
                print('\t\tSlice = {}:{}'.format(i, i_end-1))

                df_slice = df.iloc[i:i_end]
                
                for direction in directions:
                    print('\t\t\tDirection = {}'.format(direction))

                    if direction == 'arrival':
                        origins        = list(df_slice.to_records(index=False))
                        destinations   = [cities.get(city).get('city_hall_lat_lng')]
                        arrival_time   = pytz.timezone(cities.get(city).get('timezone')).localize(datetime.datetime.combine(workday, workday_tic)).timestamp()
                        distances      = distance_matrix_client.get_distance(origins=origins, destinations=destinations, mode=mode, arrival_time=arrival_time)
                        distances_file = 'data/distances-{}-{}-{}-{}-{}.json'.format(city_slug, mode, direction, i, i_end-1)
                        save_distances(distances=distances, distances_file=distances_file)
                    elif direction == 'departure':
                        origins        = [cities.get(city).get('city_hall_lat_lng')]
                        destinations   = list(df_slice.to_records(index=False))
                        departure_time = pytz.timezone(cities.get(city).get('timezone')).localize(datetime.datetime.combine(workday, workday_toc)).timestamp()
                        distances      = distance_matrix_client.get_distance(origins=origins, destinations=destinations, mode=mode, departure_time=departure_time)
                        distances_file = 'data/distances-{}-{}-{}-{}-{}.json'.format(city_slug, mode, direction, i, i_end-1)
                        save_distances(distances=distances, distances_file=distances_file)


def save_outputs():
    for city in cities.keys():
        print('City = {}'.format(city))
        city_slug   = city.lower().replace(' ', '-')
        points_file = 'data/points-{}.csv'.format(city_slug)
        df = pd.read_csv(points_file)
        for mode in modes:
            print('\tMode = {}'.format(mode))
            for i in list(range(0, len(df), 100)):
                i_end = None
                if i + 100 <= len(df):
                    i_end = i + 100
                else:
                    i_end = len(df)
                print('\t\tSlice = {}:{}'.format(i, i_end-1))
                for direction in directions:
                    print('\t\t\tDirection = {}'.format(direction))
                    distances_file = None
                    if direction == 'arrival':
                        distances_file = 'data/distances-{}-{}-{}-{}-{}.json'.format(city_slug, mode, direction, i, i_end-1)
                    elif direction == 'departure':
                        distances_file = 'data/distances-{}-{}-{}-{}-{}.json'.format(city_slug, mode, direction, i, i_end-1)
                    with open(distances_file) as f:
                        data = json.load(f)
                    
                    # Read JSON file
                    if direction == 'arrival':
                        # Get address
                        assert 'origin_addresses' in data.keys()
                        origin_addresses = data.get('origin_addresses')
                        j = 0
                        for origin_address in origin_addresses:
                            df.loc[i+j, '{}-{}-address'.format(mode, direction)] = origin_address
                            j += 1
                        # Get distance and duration
                        assert 'rows' in data.keys()
                        rows = data.get('rows')
                        j = 0
                        for row in rows:
                            assert 'elements' in row.keys()
                            elements = row.get('elements')
                            for element in elements:
                                assert 'status' in element.keys()
                                status = element.get('status')
                                if status == 'ZERO_RESULTS':
                                    # Add these to the DataFrame
                                    df.loc[i+j, '{}-{}-distance'.format(mode, direction)] = None
                                    df.loc[i+j, '{}-{}-duration'.format(mode, direction)] = None
                                elif status == 'OK':
                                    # Distance
                                    assert 'distance' in element.keys()
                                    distance = element.get('distance')
                                    assert 'value' in distance
                                    distance_value = distance.get('value')
                                    # Duration
                                    assert 'duration' in element.keys()
                                    duration = element.get('duration')
                                    assert 'value' in duration
                                    duration_value = duration.get('value')
                                    # Add these to the DataFrame
                                    df.loc[i+j, '{}-{}-distance'.format(mode, direction)] = distance_value
                                    df.loc[i+j, '{}-{}-duration'.format(mode, direction)] = duration_value
                            j += 1
                    elif direction == 'departure':
                        # Get address
                        assert 'destination_addresses' in data.keys()
                        destination_addresses = data.get('destination_addresses')
                        j = 0
                        for destination_address in destination_addresses:
                            df.loc[i+j, '{}-{}-address'.format(mode, direction)] = destination_address
                            j += 1
                        # Get distance and duration
                        assert 'rows' in data.keys()
                        rows = data.get('rows')
                        assert len(rows) == 1
                        rows0 = rows[0]
                        assert 'elements' in rows0.keys()
                        elements = rows0.get('elements')
                        j = 0
                        for element in elements:
                            assert 'status' in element.keys()
                            status = element.get('status')
                            if status == 'ZERO_RESULTS':
                                # Add these to the DataFrame
                                df.loc[i+j, '{}-{}-distance'.format(mode, direction)] = None
                                df.loc[i+j, '{}-{}-duration'.format(mode, direction)] = None
                            elif status == 'OK':
                                # Distance
                                assert 'distance' in element.keys()
                                distance = element.get('distance')
                                assert 'value' in distance
                                distance_value = distance.get('value')
                                # Duration
                                assert 'duration' in element.keys()
                                duration = element.get('duration')
                                assert 'value' in duration
                                duration_value = duration.get('value')
                                # Add these to the DataFrame
                                df.loc[i+j, '{}-{}-distance'.format(mode, direction)] = distance_value
                                df.loc[i+j, '{}-{}-duration'.format(mode, direction)] = duration_value
                            j += 1

        df.to_csv('data/results-{}.csv'.format(city_slug), index=False)


def save_outputs_no_water_nyc():
    df = pd.read_csv('data/results-new-york-city.csv')

    # Load NYC polygon, water excluded (see https://data.cityofnewyork.us/City-Government/Borough-Boundaries/tqmj-j8zm)

    

    polygons = []

    polygon_file = 'data/polygon-new-york-city-no-water.json'
    with open(polygon_file, encoding='utf-8') as f:
        data = json.load(f)

    assert 'features' in data.keys()
    features = data.get('features')
    for feature in features:
        assert 'geometry' in feature
        geometry = feature.get('geometry')
        assert 'coordinates' in geometry
        coordinates = geometry.get('coordinates')
        for coordinate in coordinates:
            assert len(coordinate) == 1
            polygons.append(Polygon(coordinate[0]))
    
    for i, row in df.iterrows():
        point = Point(row['lng'], row['lat'])
        within = False
        for polygon in polygons:
            if point.within(polygon):
                within = True
                break
        df.loc[i, 'within'] = within
    
    df.to_csv('data/results-new-york-city-no-water.csv', index=False)


if __name__ == '__main__':
    #save_inputs()
    save_outputs()
    save_outputs_no_water_nyc()