# TODO: ugh:
import sys, pprint
sys.path.extend(['.','..','py'])
import h2o, h2o_util
import os
import argparse
import time
import json

#################
# Config is below
#################

parser = argparse.ArgumentParser(
    description='Run basic H2O REST API tests.',
)

parser.add_argument('--verbose', '-v', help='verbose output', action='count')
parser.add_argument('--usecloud', help='ip:port to attach to', default='')
parser.add_argument('--host', help='hostname to attach to', default='localhost')
parser.add_argument('--port', help='port to attach to', type=int, default=54321)
args = parser.parse_args()

verbose = True if args.verbose > 0 else False
verboser = True if args.verbose > 1 else False
verbosest = True if args.verbose > 2 else False
h2o.H2O.verbose = verboser

if (len(args.usecloud) > 0):
    arr = args.usecloud.split(":")
    args.host = arr[0]
    args.port = int(arr[1])

host = args.host
port = args.port

h2o.H2O.verboseprint("host: " + str(host))
h2o.H2O.verboseprint("port" + str(port))

###########
# Utilities
pp = pprint.PrettyPrinter(indent=4)  # pretty printer for debugging

def list_to_dict(l, key):
    '''
    Given a List and a key to look for in each element return a Dict which maps the value of that key to the element.  
    Also handles nesting for the key, so you can use this for things like a list of elements which contain H2O Keys and 
    return a Dict indexed by the 'name" element within the key.
    list_to_dict([{'key': {'name': 'joe', 'baz': 17}}, {'key': {'name': 'bobby', 'baz': 42}}], 'key/name') =>
    {'joe': {'key': {'name': 'joe', 'baz': 17}}, 'bobby': {'key': {'name': 'bobby', 'baz': 42}}}
    '''
    result = {}
    for entry in l:
        # print 'In list_to_dict, entry: ', repr(entry)

        part = entry
        k = None
        for keypart in key.split('/'):
            part = part[keypart]
            k = keypart

            # print 'for keypart: ', keypart, ' part: ', repr(part)

        result[part] = entry
    # print 'result: ', repr(result)
    return result


def validate_builder(algo, builder):
    ''' Validate that a model builder seems to have a well-formed parameters list. '''
    assert 'parameters' in builder, "FAIL: Failed to find parameters list in builder: " + algo + " (" + repr(builder) + ")"
    assert isinstance(builder['parameters'], list), "FAIL: 'parameters' element is not a list in builder: " + algo + " (" + repr(builder) + ")"
    parameters = builder['parameters']
    assert len(parameters) > 0, "FAIL: parameters list is empty: " + algo + " (" + repr(builder) + ")"
    for parameter in parameters:
        h2o_util.assertKeysExist(parameter, '', ['name', 'label', 'help', 'required', 'type', 'default_value', 'actual_value', 'level', 'values'])

    assert 'can_build' in builder, "FAIL: Failed to find can_build list in builder: " + algo + " (" + repr(builder) + ")"
    assert isinstance(builder['can_build'], list), "FAIL: 'can_build' element is not a list in builder: " + algo + " (" + repr(builder) + ")"
    assert len(builder['can_build']) > 0, "FAIL: 'can_build' list is empty in builder: " + algo + " (" + repr(builder) + ")"


def validate_model_builder_result(result, original_params, model_name):
    ''' 
    Validate that a model build result has no parameter validation errors, 
    and that it has a Job with a Key.  Note that model build will return a
    Job if successful, and a ModelBuilder with errors if it's not.
    '''

    if 'validation_error_count' in result and result['validation_error_count'] > 0:
        # error case
        print 'Parameters validation error for model: ', model_name
        print 'Input parameters: '
        pp.pprint(original_params)
        print 'Returned result: '
        pp.pprint(result)
        assert result['validation_error_count'] == 0, "FAIL: Non-zero validation_error_count for model: " + model_name

    assert 'jobs' in result, "FAIL: Failed to find jobs key for model: " + model_name + ": " + pp.pprint(result)
    jobs = result['jobs']
    assert type(jobs) is list, "FAIL: Jobs element for model is not a list: " + model_name + ": " + pp.pprint(result)
    assert len(jobs) == 1, "FAIL: Jobs list for model is not 1 long: " + model_name + ": " + pp.pprint(result)
    job = jobs[0]
    assert type(job) is dict, "FAIL: Job element for model is not a dict: " + model_name + ": " + pp.pprint(result)
    assert 'key' in job, "FAIL: Failed to find key in job for model: " + model_name + ": " + pp.pprint(result)


def validate_validation_messages(result, expected_error_fields):
    '''
    Check that we got the expected ERROR validation messages for a model build or validation check with bad parameters.
    '''
    assert 'validation_error_count' in result, "FAIL: Failed to find validation_error_count in bad-parameters model build result."
    assert 0 < result['validation_error_count'], "FAIL: 0 != validation_error_count in bad-parameters model build validation result."

    error_fields = []
    for validation_message in result['validation_messages']:
        if validation_message['message_type'] == 'ERROR':
            error_fields.append(validation_message['field_name'])

    not_found = [item for item in expected_error_fields if item not in error_fields]
    assert len(not_found) == 0, 'FAIL: Failed to find all expected ERROR validation messages.  Missing: ' + repr(not_found) + ' from result: ' + repr(error_fields)
    assert len(not_found) == 0, 'FAIL: Failed to find all expected ERROR validation messages.  Missing: ' + repr(not_found) + ' from result: ' + repr(result['validation_messages'])


def validate_model_exists(model_name, models):
    '''
    Validate that a given model key is found in the models list.
    '''
    models_dict = list_to_dict(models, 'key/name')
    assert model_name in models_dict, "FAIL: Failed to find " + model_name + " in models list: " + repr(models_dict.keys())
    return models_dict[model_name]


def validate_actual_parameters(input_parameters, actual_parameters, training_frame, validation_frame):
    '''
    Validate that the returned parameters list for a model build contains all the values we passed in as input.
    '''
    actuals_dict = list_to_dict(actual_parameters, 'name')
    for k, expected in input_parameters.iteritems():
        # TODO: skipping some stuff for now because they aren't serialized properly
        if k is 'response_column':
            continue

        # TODO: skipping training frame becuase model building is now changing the training frame.  Why?!
        if k is 'training_frame':
            continue

        # Python says True; json says true
        assert k in actuals_dict, "FAIL: Expected key " + k + " not found in actual parameters list."

        actual = actuals_dict[k]['actual_value']
        actual_type = actuals_dict[k]['type']

        # print repr(actuals_dict[k])
        if actual_type == 'boolean':
            expected = bool(expected)
            actual = True if 'true' == actual else False # true -> True
        elif actual_type == 'int':
            expected = int(expected)
            actual = int(actual)
        elif actual_type == 'long':
            expected = long(expected)
            actual = long(actual)
        elif actual_type == 'string':
            expected = str(expected)
            actual = str(actual)
        elif actual_type == 'double':
            expected = float(expected)
            actual = float(actual)
        elif actual_type == 'float':
            expected = float(expected)
            actual = float(actual)
        elif actual_type.startswith('Key<'):
            # For keys we send just a String but receive an object
            expected = expected
            actual = json.loads(actual)['name']
            
        # TODO: don't do exact comparison of floating point!

        assert expected == actual, "FAIL: Parameter with name: " + k + " expected to have input value: " + str(expected) + ", instead has: " + str(actual) + " cast from: " + str(actuals_dict[k]['actual_value']) + " ( type of expected: " + str(type(expected)) + ", type of actual: " + str(type(actual)) + ")"
    # TODO: training_frame, validation_frame


def validate_predictions(result, model_name, frame_key, expected_rows):
    '''
    Validate a /Predictions result.
    '''
    assert p is not None, "FAIL: Got a null result for scoring: " + model_name + " on: " + frame_key
    assert 'model_metrics' in p, "FAIL: Predictions for scoring: " + model_name + " on: " + frame_key + " does not contain a model_metrics object."
    mm = p['model_metrics'][0]
    h2o.H2O.verboseprint('mm: ', repr(mm))
    assert 'auc' in mm, "FAIL: Predictions for scoring: " + model_name + " on: " + frame_key + " does not contain an AUC."
    assert 'cm' in mm, "FAIL: Predictions for scoring: " + model_name + " on: " + frame_key + " does not contain a CM."
    assert 'predictions' in mm, "FAIL: Predictions for scoring: " + model_name + " on: " + frame_key + " does not contain an predictions section."
    assert 'key' in mm['predictions'], "FAIL: Predictions for scoring: " + model_name + " on: " + frame_key + " does not contain a key."
    assert 'name' in mm['predictions']['key'], "FAIL: Predictions for scoring: " + model_name + " on: " + frame_key + " does not contain a key name."
    
    predictions_key = mm['predictions']['key']['name']
    result = a_node.frames(key=predictions_key, find_compatible_models=True, len=5)
    frames = result['frames']
    frames_dict = h2o_util.list_to_dict(frames, 'key/name')
    assert predictions_key in frames_dict, "FAIL: Failed to find predictions key" + predictions_key + " in Frames list."
    
    predictions = mm['predictions']
    h2o.H2O.verboseprint('p: ', repr(p))
    assert 'columns' in predictions, "FAIL: Predictions for scoring: " + model_name + " on: " + frame_key + " does not contain an columns section."
    assert len(predictions['columns']) > 0, "FAIL: Predictions for scoring: " + model_name + " on: " + frame_key + " does not contain any columns."
    assert 'label' in predictions['columns'][0], "FAIL: Predictions for scoring: " + model_name + " on: " + frame_key + " column 0 has no label element."
    assert 'predict' == predictions['columns'][0]['label'], "FAIL: Predictions for scoring: " + model_name + " on: " + frame_key + " column 0 is not 'predict'."
    assert expected_rows == predictions['rows'], "FAIL: Predictions for scoring: " + model_name + " on: " + frame_key + " has an unexpected number of rows."


def cleanup(a_node, models=None, frames=None):
    '''
    DELETE the specified models and frames from H2O.
    '''
    ###################
    # test delete_model
    if models is None:
        a_node.delete_models()
    else:
        for model in models:
            a_node.delete_model(model)

    ms = a_node.models()
    if models is None:
        assert 'models' in ms and 0 == len(ms['models']), "FAIL: Called delete_models and the models list isn't empty: " + h2o_util.dump_json(ms)
    else:
        for model in models:
            for m in ms['models']:
                assert m['key'] != model, 'FAIL: Found model that we tried to delete in the models list: ' + model

    ###################
    # test delete_frame
    if frames is not None:
        for frame in frames:
            a_node.delete_frame(frame)
            ms = a_node.frames(len=5)

            found = False;
            for m in ms['frames']:
                assert m['key'] != frame, 'FAIL: Found frame that we tried to delete in the frames list: ' + frame
            

    # TODO
    ####################
    # test delete_models
    # jobs = a_node.build_model(algo='kmeans', destination_key='dummy', training_frame='prostate_binomial', parameters={'k': 2 }, timeoutSecs=240) # synchronous
    # a_node.delete_models()
    # models = a_node.models()

    # assert 'models' in models and 0 == len(models['models']), "FAIL: Called delete_models and the models list isn't empty: " + h2o_util.dump_json(models)

    # TODO
    ####################
    # test delete_frames


class ModelSpec(dict):
    ''' 
    Dictionary which specifies all that's needed to build and validate a model.
    '''
    def __init__(self, dest_key, algo, frame_key, params, model_category):
        self['algo'] = algo
        self['frame_key'] = frame_key
        self['params'] = params
        self['model_category'] = model_category

        if dest_key is None:
            self['dest_key'] = algo + "_" + frame_key
        else:
            self['dest_key'] = dest_key

    @staticmethod
    def for_dataset(dest_key, algo, dataset, params):
        ''' 
        Factory for creating a ModelSpec for a given Dataset (frame and additional metadata). 
        '''
        dataset_params = {}
        assert 'model_category' in dataset, "FAIL: Failed to find model_category in dataset: " + repr(dataset)
        if 'response_column' in dataset: dataset_params['response_column'] = dataset['response_column']
        if 'ignored_columns' in dataset: dataset_params['ignored_columns'] = repr(dataset['ignored_columns'])
        if dataset['model_category'] == 'Binomial' or dataset['model_category'] == 'Multinomial': 
            dataset_params['do_classification'] = True
        elif dataset['model_category'] == 'Clustering':
            pass
        else:
            dataset_params['do_classification'] = False

        return ModelSpec(dest_key, algo, dataset['dest_key'], dict(dataset_params.items() + params.items()), dataset['model_category'])
    

    def build_and_validate_model(self, a_node):
        before = time.time()
        if verbose: print 'About to build: ' + self['dest_key'] + ', a ' + self['algo'] + ' model on frame: ' + self['frame_key'] + ' with params: ' + repr(self['params'])
        result = a_node.build_model(algo=self['algo'], destination_key=self['dest_key'], training_frame=self['frame_key'], parameters=self['params'], timeoutSecs=240) # synchronous
        validate_model_builder_result(result, self['params'], self['dest_key'])

        model = validate_model_exists(self['dest_key'], a_node.models()['models'])
        validate_actual_parameters(self['params'], model['parameters'], self['frame_key'], None)

        # TODO: refactor into helper
        assert 'output' in model, 'FAIL: Failed to find output object in model: ' + self['dest_key']
        assert 'model_category' in model['output'], 'FAIL: Failed to find model_category in model: ' + self['dest_key']
        assert model['output']['model_category'] == self['model_category'], 'FAIL: Expected model_category: ' + self['model_category'] + ' but got: ' + model['output']['model_category'] + ' for model: ' + self['dest_key']

        if verbose: print 'Done building: ' + self['dest_key'] + " (" + str(time.time() - before) + ")"
        return model


### TODO: we should be able to have multiple DatasetSpecs that come from a single parse, for efficiency
class DatasetSpec(dict):
    '''
    Dictionary which specifies the properties of a Frame (Dataset) for a specific use 
    (e.g., prostate data with binomial classification on the CAPSULE column 
    OR prostate data with regression on the AGE column).
    '''
    def __init__(self, dest_key, path, expected_rows, model_category, response_column, ignored_columns):
        self['path'] = os.path.realpath(path)
        self['expected_rows'] = expected_rows
        self['model_category'] = model_category
        self['response_column'] = response_column
        self['ignored_columns'] = ignored_columns

        if dest_key == None:
            # specify dest_key every time
            basename = os.path.basename(path)
            basename_split = basename.split(".")
            if len(basename_split) == 1:
                self['dest_key'] = basename_split[0] + ".hex" # name + ".hex"
            else:
                self['dest_key'] = basename_split[-2] + ".hex" # name without suffix + ".hex"
        else:
            self['dest_key'] = dest_key


    def import_and_validate_dataset(self, a_node):
        global verbose, verboser, verbosest

        if verbose: print "About to import and validate: " + self['path']
        import_result = a_node.import_files(path=self['path'])
        if h2o.H2O.verbose:
            print "import_result: "
            pp.pprint(import_result)
            print "frames: "
            pp.pprint(a_node.frames(key=import_result['keys'][0], len=5))

        frames = a_node.frames(key=import_result['keys'][0], len=5)['frames']
        assert frames[0]['isText'], "FAIL: Raw imported Frame is not isText: " + repr(frames[0])
        parse_result = a_node.parse(key=import_result['keys'][0], dest_key=self['dest_key']) # TODO: handle multiple files
        key = parse_result['frames'][0]['key']['name']
        assert key == self['dest_key'], 'FAIL: Imported frame key is wrong; expected: ' + self['dest_key'] + ', got: ' + key
        assert self['expected_rows'] == parse_result['frames'][0]['rows'], 'FAIL: Imported frame number of rows is wrong; expected: ' + str(self['expected_rows']) + ', got: ' + str(parse_result['frames'][0]['rows'])

        self['dataset'] = parse_result['frames'][0]  # save the imported dataset object

        if verbose: print "Imported and validated key: " + self['dataset']['key']['name']
        return self['dataset']


################
# The test body:
################

a_node = h2o.H2O(host, port)

#########
# Config:
algos = ['example', 'kmeans', 'deeplearning', 'glm', 'gbm', 'word2vec', 'quantile', 'grep', 'splitframe']
algo_additional_default_params = { 'grep' : { 'regex' : '.*' },
                                   'kmeans' : { 'k' : 2 }
                                 } # additional params to add to the default params
clean_up_after = False

h2o.H2O.verboseprint("connected to: ", "127.0.0.1", 54321)

models = a_node.models()
if h2o.H2O.verbose:
    print 'Models: '
    pp.pprint(models)

models = a_node.models(api_version=92)
if h2o.H2O.verbose:
    print 'ModelsV92: '
    pp.pprint(models)

frames = a_node.frames(len=5)
if h2o.H2O.verbose:
    print 'Frames: '
    pp.pprint(frames)

####################################
# test schemas collection GET
# print 'Testing /Metadata/schemas. . .'
# schemas = a_node.schemas(timeoutSecs=240)
# 
# # if h2o.H2O.verbose:
# print 'Schemas: '
# pp.pprint(schemas)


####################################
# test schemas individual GET
# print 'Testing /Metadata/schemas/FrameV2. . .'
# schema = a_node.schema(schemaname='FrameV2', timeoutSecs=240)
# 
# if h2o.H2O.verbose:
#     print 'Schema: '
#     pp.pprint(schema)







####################################
# test model_builders collection GET
if verbose: print 'Testing /ModelBuilders. . .'
model_builders = a_node.model_builders(timeoutSecs=240)

if h2o.H2O.verbose:
    print 'ModelBuilders: '
    pp.pprint(model_builders)

for algo in algos:
    assert algo in model_builders['model_builders'], "FAIL: Failed to find algo: " + algo
    builder = model_builders['model_builders'][algo]
    validate_builder(algo, builder)
    

####################################
# test model_builders individual GET
if verbose: print 'Testing /ModelBuilders/{algo}. . .'
for algo in algos:
    model_builder = a_node.model_builders(algo=algo, timeoutSecs=240)
    assert algo in model_builder['model_builders'], "FAIL: Failed to find algo: " + algo
    builder = model_builders['model_builders'][algo]
    validate_builder(algo, builder)

####################################
# test model_metrics collection GET
if verbose: print 'Testing /ModelMetrics. . .'
model_metrics = a_node.model_metrics(timeoutSecs=240)

if h2o.H2O.verbose:
    print 'ModelMetrics: '
    pp.pprint(model_metrics)

####################################
# test model_metrics individual GET
# TODO

# Clean up frames
if verbose: print 'Cleaning up old stuff. . .'
cleanup(a_node)


####################################################################################################
# Import and check datasets
####################################################################################################
# dest_key, path, expected_rows, model_category, response_column, ignored_columns
datasets_to_import = [
    DatasetSpec('prostate_clustering', '../../smalldata/logreg/prostate.csv', 380, 'Clustering', None, ['ID']),
    DatasetSpec('prostate_binomial', '../../smalldata/logreg/prostate.csv', 380, 'Binomial', 'CAPSULE', ['ID']),
    DatasetSpec('prostate_regression', '../../smalldata/logreg/prostate.csv', 380, 'Regression', 'AGE', ['ID']),

    DatasetSpec('airlines_binomial', '../../smalldata/airlines/allyears2k_headers.zip', 43978, 'Binomial', 'IsDepDelayed', ['IsArrDelayed', 'ArrDelay', 'DepDelay']), # TODO: more ignored?

    DatasetSpec('iris_multinomial', '../../smalldata/iris/iris_wheader.csv', 150, 'Multinomial', 'class', []),
]

datasets = {} # the dataset spec
for dataset_spec in datasets_to_import:
    dataset = dataset_spec.import_and_validate_dataset(a_node) # it's also stored in dataset_spec['dataset']
    datasets[dataset_spec['dest_key']] = dataset_spec


################################################
# Test /Frames for prostate.csv
frames = a_node.frames(len=5)['frames']
frames_dict = h2o_util.list_to_dict(frames, 'key/name')

# TODO: remove:
if h2o.H2O.verbose:
    print "frames: "
    pp.pprint(frames)

if h2o.H2O.verbose:
    print "frames_dict: "
    pp.pprint(frames_dict)

# TODO: test len and offset (they aren't working yet)
assert 'prostate_binomial' in frames_dict, "FAIL: Failed to find " + 'prostate_binomial' + " in Frames list."
assert not frames_dict['prostate_binomial']['isText'], "FAIL: Parsed Frame is isText"


# Test /Frames/{key} for prostate.csv
frames = a_node.frames(key='prostate_binomial', len=5)['frames']
frames_dict = h2o_util.list_to_dict(frames, 'key/name')
assert 'prostate_binomial' in frames_dict, "FAIL: Failed to find prostate.hex in Frames list."
columns_dict = h2o_util.list_to_dict(frames[0]['columns'], 'label')
assert 'CAPSULE' in columns_dict, "FAIL: Failed to find CAPSULE in Frames/prostate.hex."
assert 'AGE' in columns_dict, "FAIL: Failed to find AGE in Frames/prostate.hex/columns."
assert 'bins' in columns_dict['AGE'], "FAIL: Failed to find bins in Frames/prostate.hex/columns/AGE."
h2o.H2O.verboseprint('bins: ' + repr(columns_dict['AGE']['bins']))
assert None is columns_dict['AGE']['bins'], "FAIL: Failed to clear bins field." # should be cleared except for /summary


# Test /Frames/{key}/columns for prostate.csv
frames = a_node.columns(key='prostate_binomial')['frames']
columns_dict = h2o_util.list_to_dict(frames[0]['columns'], 'label')
assert 'ID' in columns_dict, "FAIL: Failed to find ID in Frames/prostate.hex/columns."
assert 'AGE' in columns_dict, "FAIL: Failed to find AGE in Frames/prostate.hex/columns."
assert 'bins' in columns_dict['AGE'], "FAIL: Failed to find bins in Frames/prostate.hex/columns/AGE."
h2o.H2O.verboseprint('bins: ' + repr(columns_dict['AGE']['bins']))
assert None is columns_dict['AGE']['bins'], "FAIL: Failed to clear bins field." # should be cleared except for /summary

# Test /Frames/{key}/columns/{label} for prostate.csv
frames = a_node.column(key='prostate_binomial', column='AGE')['frames']
columns_dict = h2o_util.list_to_dict(frames[0]['columns'], 'label')
assert 'AGE' in columns_dict, "FAIL: Failed to find AGE in Frames/prostate.hex/columns."
assert 'bins' in columns_dict['AGE'], "FAIL: Failed to find bins in Frames/prostate.hex/columns/AGE."
h2o.H2O.verboseprint('bins: ' + repr(columns_dict['AGE']['bins']))
assert None is columns_dict['AGE']['bins'], "FAIL: Failed to clear bins field." # should be cleared except for /summary

# Test /Frames/{key}/columns/{label}/summary for prostate.csv
frames = a_node.summary(key='prostate_binomial', column='AGE')['frames']
columns_dict = h2o_util.list_to_dict(frames[0]['columns'], 'label')
assert 'AGE' in columns_dict, "FAIL: Failed to find AGE in Frames/prostate.hex/columns/AGE/summary."
col = columns_dict['AGE']
h2o_util.assertKeysExistAndNonNull(col, '', ['label', 'missing', 'zeros', 'pinfs', 'ninfs', 'mins', 'maxs', 'mean', 'sigma', 'type', 'data', 'precision', 'bins', 'base', 'stride', 'pctiles'])
h2o_util.assertKeysExist(col, '', ['domain', 'str_data'])
assert col['mins'][0] == 43, 'FAIL: Failed to find 43 as the first min for AGE.'
assert col['maxs'][0] == 79, 'FAIL: Failed to find 79 as the first max for AGE.'
assert col['mean'] == 66.03947368421052, 'FAIL: Failed to find 66.03947368421052 as the mean for AGE.'
assert col['sigma'] == 6.527071269173308, 'FAIL: Failed to find 6.527071269173308 as the sigma for AGE.'
assert col['type'] == 'int', 'FAIL: Failed to find int as the type for AGE.'
assert col['data'][0] == 65, 'FAIL: Failed to find 65 as the first data for AGE.'
assert col['precision'] == -1, 'FAIL: Failed to find -1 as the precision for AGE.'
assert col['bins'][0] == 1, 'FAIL: Failed to find 1 as the first bin for AGE.'
assert col['base'] == 43, 'FAIL: Failed to find 43 as the base for AGE.'
assert col['stride'] == 1, 'FAIL: Failed to find 1 as the stride for AGE.'
assert col['pctiles'][0] == 50.5, 'FAIL: Failed to find 50.5 as the first pctile for AGE.'


####################################################################################################
# Build and do basic validation checks on models
####################################################################################################
models_to_build = [
    ModelSpec.for_dataset('kmeans_prostate', 'kmeans', datasets['prostate_clustering'], { 'k': 2 } ),

    ModelSpec.for_dataset('glm_prostate_regression', 'glm', datasets['prostate_regression'], { } ),

    ModelSpec.for_dataset('glm_prostate_binomial', 'glm', datasets['prostate_binomial'], {'family': 'binomial'} ),
    # TODO: Crashes: ModelSpec('glm_airlines_binomial', 'glm', 'airlines_binomial', {'response_column': 'IsDepDelayed', 'do_classification': True, 'family': 'binomial'}, 'Binomial'),
    # Multinomial doesn't make sense for glm: ModelSpec('glm_iris_multinomial', 'glm', iris_multinomial, {'response_column': 'class', 'do_classification': True, 'family': 'gaussian'}, 'Regression'),

    ModelSpec.for_dataset('deeplearning_prostate_regression', 'deeplearning', datasets['prostate_regression'], { 'epochs': 1 } ),
    ModelSpec.for_dataset('deeplearning_prostate_binomial', 'deeplearning', datasets['prostate_binomial'], { 'epochs': 1, 'hidden': '[20, 20]' } ),
    ModelSpec.for_dataset('deeplearning_airlines_binomial', 'deeplearning', datasets['airlines_binomial'], { 'epochs': 1, 'hidden': '[10, 10]' } ),
    ModelSpec.for_dataset('deeplearning_iris_multinomial', 'deeplearning', datasets['iris_multinomial'], { 'epochs': 1 } ),

    ModelSpec.for_dataset('gbm_prostate_regression', 'gbm', datasets['prostate_regression'], { 'ntrees': 5 } ),
    ModelSpec.for_dataset('gbm_prostate_binomial', 'gbm', datasets['prostate_binomial'], { 'ntrees': 5 } ),
    ModelSpec.for_dataset('gbm_airlines_binomial', 'gbm', datasets['airlines_binomial'], { 'ntrees': 5 } ),
    ModelSpec.for_dataset('gbm_iris_multinomial', 'gbm', datasets['iris_multinomial'], { 'ntrees': 5 } ),
]

built_models = {}
for model_spec in models_to_build:
    model = model_spec.build_and_validate_model(a_node)
    built_models[model_spec['dest_key']] = model


#######################################
# Test default parameters validation for each model builder
#
model_builders = a_node.model_builders(timeoutSecs=240)['model_builders']

# Do we know about all of them?
server_algos = model_builders.keys()
assert len(set(server_algos) - set(algos)) == 0, "FAIL: Our set of algos doesn't match what the server knows about.  Ours: " + repr(algos) + "; server's: " + repr(server_algos)

for algo, model_builder in model_builders.iteritems():
    parameters_list = model_builder['parameters']
    test_parameters = { value['name'] : value['default_value'] for value in parameters_list } # collect default parameters
    if algo in algo_additional_default_params:
        test_parameters.update(algo_additional_default_params[algo])

    parameters_validation = a_node.validate_model_parameters(algo=algo, training_frame=None, parameters=test_parameters, timeoutSecs=240) # synchronous
    assert 'validation_error_count' in parameters_validation, "FAIL: Failed to find validation_error_count in good-parameters parameters validation result."
    h2o.H2O.verboseprint("Bad params validation messages: ", repr(parameters_validation))
    
    expected_count = 1
    if expected_count != parameters_validation['validation_error_count']:
        print "validation errors: "
        pp.pprint(parameters_validation)
    assert expected_count == parameters_validation['validation_error_count'], "FAIL: " + str(expected_count) + " != validation_error_count in good-parameters parameters validation result."
    assert 'training_frame' == parameters_validation['validation_messages'][0]['field_name'], "FAIL: First validation message is about missing training frame."


#######################################
# Test DeepLearning parameters validation
#
# Default parameters:
model_builder = a_node.model_builders(algo='deeplearning', timeoutSecs=240)['model_builders']['deeplearning']
dl_test_parameters_list = model_builder['parameters']
dl_test_parameters = {value['name'] : value['default_value'] for value in dl_test_parameters_list}

parameters_validation = a_node.validate_model_parameters(algo='deeplearning', training_frame=None, parameters=dl_test_parameters, timeoutSecs=240) # synchronous
assert 'validation_error_count' in parameters_validation, "FAIL: Failed to find validation_error_count in good-parameters parameters validation result."
h2o.H2O.verboseprint("Bad params validation messages: ", repr(parameters_validation))
if 1 != parameters_validation['validation_error_count']:
    print "validation errors: "
    pp.pprint(parameters_validation)
assert 1 == parameters_validation['validation_error_count'], "FAIL: 1 != validation_error_count in good-parameters parameters validation result."
assert 'training_frame' == parameters_validation['validation_messages'][0]['field_name'], "FAIL: First validation message is about missing training frame."

# Good parameters (note: testing with null training_frame):
dl_test_parameters = {'response_column': 'CAPSULE', 'hidden': "[10, 20, 10]" }
parameters_validation = a_node.validate_model_parameters(algo='deeplearning', training_frame=None, parameters=dl_test_parameters, timeoutSecs=240) # synchronous
assert 'validation_error_count' in parameters_validation, "FAIL: Failed to find validation_error_count in good-parameters parameters validation result."
h2o.H2O.verboseprint("Bad params validation messages: ", repr(parameters_validation))
if 1 != parameters_validation['validation_error_count']:
    print "validation errors: "
    pp.pprint(parameters_validation)
assert 1 == parameters_validation['validation_error_count'], "FAIL: 1 != validation_error_count in good-parameters parameters validation result."
assert 'training_frame' == parameters_validation['validation_messages'][0]['field_name'], "FAIL: First validation message is about missing training frame."

# Bad parameters (hidden is null):
# (note: testing with null training_frame)
dl_test_parameters = {'response_column': 'CAPSULE', 'hidden': "[10, 20, 10]", 'input_dropout_ratio': 27 }
parameters_validation = a_node.validate_model_parameters(algo='deeplearning', training_frame=None, parameters=dl_test_parameters, timeoutSecs=240) # synchronous
assert 'validation_error_count' in parameters_validation, "FAIL: Failed to find validation_error_count in bad-parameters parameters validation result."
h2o.H2O.verboseprint("Good params validation messages: ", repr(parameters_validation))
assert 2 == parameters_validation['validation_error_count'], "FAIL: 2 != validation_error_count in bad-parameters parameters validation result."
assert 'training_frame' == parameters_validation['validation_messages'][0]['field_name'], "FAIL: First validation message is about missing training frame."

found_expected_error = False
for validation_message in parameters_validation['validation_messages']:
    if validation_message['message_type'] == 'ERROR' and validation_message['field_name'] == 'input_dropout_ratio':
        found_expected_error = True
assert found_expected_error, "FAIL: Failed to find error message about input_dropout_ratio in the validation messages."

#######################################
# Try to build DeepLearning model for Prostate but with bad parameters; we should get a ModelParametersSchema with the error.
if verbose: print 'About to try to build a DeepLearning model with bad parameters. . .'
dl_prostate_bad_parameters = {'response_column': 'CAPSULE', 'hidden': "[10, 20, 10]", 'input_dropout_ratio': 27  }
parameters_validation = a_node.build_model(algo='deeplearning', destination_key='deeplearning_prostate_binomial_bad', training_frame='prostate_binomial', parameters=dl_prostate_bad_parameters, timeoutSecs=240) # synchronous
validate_validation_messages(parameters_validation, ['input_dropout_ratio'])
if verbose: print 'Done trying to build DeepLearning model with bad parameters.'

###################################
# Compute and check ModelMetrics for 'deeplearning_prostate_binomial'
mm = a_node.compute_model_metrics(model='deeplearning_prostate_binomial', frame='prostate_binomial')
assert mm is not None, "FAIL: Got a null result for scoring: " + 'deeplearning_prostate_binomial' + " on: " + 'prostate_binomial'
assert 'model_category' in mm, "FAIL: ModelMetrics for scoring: " + 'deeplearning_prostate_binomial' + " on: " + 'prostate_binomial' + " does not contain a model_category."
assert 'Binomial' == mm['model_category'], "FAIL: ModelMetrics for scoring: " + 'deeplearning_prostate_binomial' + " on: " + 'prostate_binomial' + " model_category is not Binomial, it is: " + str(mm['model_category'])
assert 'auc' in mm, "FAIL: ModelMetrics for scoring: " + 'deeplearning_prostate_binomial' + " on: " + 'prostate_binomial' + " does not contain an AUC."
assert 'cm' in mm, "FAIL: ModelMetrics for scoring: " + 'deeplearning_prostate_binomial' + " on: " + 'prostate_binomial' + " does not contain a CM."
h2o.H2O.verboseprint("ModelMetrics for scoring: ", 'deeplearning_prostate_binomial', " on: ", 'prostate_binomial', ":  ", repr(mm))

###################################
# Check for ModelMetrics for 'deeplearning_prostate_binomial' in full list
mms = a_node.model_metrics() # fetch all
assert 'model_metrics' in mms, 'FAIL: Failed to find model_metrics in result of /3/ModelMetrics.'
found_mm = False
for mm in mms['model_metrics']:
    assert 'model' in mm, "FAIL: mm does not contain a model element: " + repr(mm)
    assert 'name' in mm['model'], "FAIL: mm[model] isn't a key with a name: " + repr(mm)
    assert 'type' in mm['model'], "FAIL: mm[model] does not contain a type: " + repr(mm)
    assert 'Key<Model>' == mm['model']['type'], "FAIL: mm[model] type is not Key<Model>: " + repr(mm)

    assert 'frame' in mm, "FAIL: mm does not contain a frame element: " + repr(mm)
    assert 'name' in mm['frame'], "FAIL: mm[frame] does not contain a name: " + repr(mm)
    assert 'type' in mm['frame'], "FAIL: mm[frame] does not contain a type: " + repr(mm)
    assert 'Key<Frame>' == mm['frame']['type'], "FAIL: mm[frame] type is not Key<Frame>: " + repr(mm)

    model_key = mm['model']['name']
    frame_key = mm['frame']['name'] # TODO: should match
    if model_key == 'deeplearning_prostate_binomial' and frame_key == 'prostate_binomial':
        found_mm = True
assert found_mm, "FAIL: Failed to find ModelMetrics object for model: " + 'deeplearning_prostate_binomial' + " and frame: " + 'prostate_binomial'

###################################
# Predict and check ModelMetrics for 'deeplearning_prostate_binomial'
p = a_node.predict(model='deeplearning_prostate_binomial', frame='prostate_binomial')
validate_predictions(p, 'deeplearning_prostate_binomial', 'prostate_binomial', 380)
h2o.H2O.verboseprint("Predictions for scoring: ", 'deeplearning_prostate_binomial', " on: ", 'prostate_binomial', ":  ", repr(p))

###################################
# Predict and check ModelMetrics for 'deeplearning_prostate_regression'
p = a_node.predict(model='deeplearning_prostate_regression', frame='prostate_binomial')
validate_predictions(p, 'deeplearning_prostate_regression', 'prostate_binomial', 380)
h2o.H2O.verboseprint("Predictions for scoring: ", 'deeplearning_prostate_regression', " on: ", 'prostate_binomial', ":  ", repr(p))

###################################
# Predict and check ModelMetrics for 'gbm_prostate_binomial'
p = a_node.predict(model='gbm_prostate_binomial', frame='prostate_binomial')
validate_predictions(p, 'gbm_prostate_binomial', 'prostate_binomial', 380)
h2o.H2O.verboseprint("Predictions for scoring: ", 'gbm_prostate_binomial', " on: ", 'prostate_binomial', ":  ", repr(p))

###################################
# Predict and check ModelMetrics for 'gbm_prostate_regression'
p = a_node.predict(model='gbm_prostate_regression', frame='prostate_binomial')
validate_predictions(p, 'gbm_prostate_regression', 'prostate_binomial', 380)
h2o.H2O.verboseprint("Predictions for scoring: ", 'gbm_prostate_regression', " on: ", 'prostate_binomial', ":  ", repr(p))

###################################
# Predict and check ModelMetrics (empty now except for predictions frame) for 'kmeans_prostate'
p = a_node.predict(model='kmeans_prostate', frame='prostate_binomial')
validate_predictions(p, 'kmeans_prostate', 'prostate_binomial', 380)
h2o.H2O.verboseprint("Predictions for scoring: ", 'kmeans_prostate', " on: ", 'prostate_binomial', ":  ", repr(p))

######################################################################
# Now look for kmeans_prostate_model_name using the one-model API and find_compatible_frames, and check it
model = a_node.models(key='kmeans_prostate', find_compatible_frames=True)
found_kmeans = False;
h2o.H2O.verboseprint('k-means model with find_compatible_frames output: ')
h2o.H2O.verboseprint('/Models/', 'kmeans_prostate', '?find_compatible_frames=true: ', repr(model))
h2o_util.assertKeysExist(model['models'][0], '', ['compatible_frames'])
assert 'prostate_binomial' in model['models'][0]['compatible_frames'], "FAIL: Failed to find " + 'prostate_binomial' + " in compatible_frames list."


######################################################################
# Now look for 'prostate_binomial' using the one-frame API and find_compatible_models, and check it
result = a_node.frames(key='prostate_binomial', find_compatible_models=True, len=5)
frames = result['frames']
frames_dict = h2o_util.list_to_dict(frames, 'key/name')
assert 'prostate_binomial' in frames_dict, "FAIL: Failed to find prostate.hex in Frames list."

compatible_models = result['compatible_models']
models_dict = h2o_util.list_to_dict(compatible_models, 'key/name')
assert 'deeplearning_prostate_binomial' in models_dict, "FAIL: Failed to find " + 'deeplearning_prostate_binomial' + " in compatible models list."

assert 'deeplearning_prostate_binomial' in frames[0]['compatible_models'], "FAIL: failed to find deeplearning_prostate_binomial in compatible_models for prostate."
assert 'kmeans_prostate' in frames[0]['compatible_models'], "FAIL: failed to find kmeans_prostate in compatible_models for prostate."
h2o.H2O.verboseprint('/Frames/prosate.hex?find_compatible_models=true: ', repr(result))

# TODO: use built_models
if clean_up_after:
    cleanup(models=[dl_airlines_model_name, 'deeplearning_prostate_binomial', 'kmeans_prostate'], frames=['prostate_binomial', 'airlines_binomial'])


