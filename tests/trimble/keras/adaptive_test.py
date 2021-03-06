import numpy as np
import tensorflow as tf
import keras.backend as K
from keras.models import Model
from keras.layers import Input, Lambda, Embedding
from keras import initializers
from trimble.keras import adaptive

def test_build_cluster_weight_shapes():
    assert [(1000, 5002), (256, 2000), (64, 3000)] == adaptive.build_cluster_weight_shapes([1000, 256, 64], [5000, 7000, 10000])
    assert [(8, 5002), (2, 2000), (2, 3000)] == adaptive.build_cluster_weight_shapes([8, 2, 2], [5000, 7000, 10000])

def test_build_cluster_projection_shapes():
    assert [None, (1000, 256), (1000, 64)] == adaptive.build_cluster_projection_shapes(1000, [1000, 256, 64])
    assert [(2048, 1000), (2048, 256), (2048, 64)] == adaptive.build_cluster_projection_shapes(2048, [1000, 256, 64])

def test_compute_child_cluster_masks():
    cutoffs = [3000, 5000, 7000, 10000]
    labels = np.array([[5586, 3971, 7741, 1349, 2822],
                       [3422, 1215, 6291, 7520, 1730],
                       [8577, 2887, 1507, 9086, 2399],
                       [4154, 7241, 1640, 3606, 9889],
                       [6227, 6129,  637, 8587, 1059],
                       [5079, 1630, 8016, 5110, 1078],
                       [2296, 1792, 7380, 1217, 3860],
                       [5159,  681, 8546, 2018, 5645],
                       [ 506, 3150, 6184, 6312, 2690],
                       [ 448,  982, 5918, 1128, 3960]], dtype='int32')
    labels = np.expand_dims(labels, axis=-1)

    with tf.Session() as session:
        inputs = tf.constant(labels)
        cluster_masks = session.run(adaptive.compute_child_cluster_masks(inputs, cutoffs))
        assert [3971, 3422, 4154, 3606, 3860, 3150, 3960] == labels[cluster_masks[0]].tolist()
        assert [5586, 6291, 6227, 6129, 5079, 5110, 5159, 5645, 6184, 6312, 5918] == labels[cluster_masks[1]].tolist()
        assert [7741, 7520, 8577, 9086, 7241, 9889, 8587, 8016, 7380, 8546] == labels[cluster_masks[2]].tolist()

def test_compute_prob():
    # with timesteps
    with tf.Session() as sess:
        c1 = tf.constant(np.random.random((10, 5, 12)))
        c2 = tf.constant(np.random.random((10, 5, 10)))
        c3 = tf.constant(np.random.random((10, 5, 20)))
        result = sess.run(adaptive.compute_prob([c1, c2, c3], [10, 20, 40]))
        # did we get the right shape?
        assert (10, 5, 40) == result.shape
        # do we have a valid probability distribution?
        prob_sum = np.sum(result, axis=-1)
        assert np.all((prob_sum > 0.99999) & (prob_sum < 1.00001))

    # without timesteps
    with tf.Session() as sess:
        c1 = tf.constant(np.random.random((10, 12)))
        c2 = tf.constant(np.random.random((10, 10)))
        c3 = tf.constant(np.random.random((10, 20)))
        result = sess.run(adaptive.compute_prob([c1, c2, c3], [10, 20, 40]))
        # did we get the right shape?
        assert (10, 40) == result.shape
        # do we have a valid probability distribution?
        prob_sum = np.sum(result, axis=-1)
        assert np.all((prob_sum > 0.99999) & (prob_sum < 1.00001))


def test_compute_logprob():
    # with timesteps
    with tf.Session() as sess:
        c1 = tf.constant(np.random.random((10, 5, 12)))
        c2 = tf.constant(np.random.random((10, 5, 10)))
        c3 = tf.constant(np.random.random((10, 5, 20)))
        result = sess.run(adaptive.compute_logprob([c1, c2, c3], [10, 20, 40]))
        # did we get the right shape?
        assert (10, 5, 40) == result.shape
        # do we have a valid probability distribution?
        prob_sum = np.sum(np.exp(result), axis=-1)
        assert np.all((prob_sum > 0.99999) & (prob_sum < 1.00001))

    # without timesteps
    with tf.Session() as sess:
        c1 = tf.constant(np.random.random((10, 12)))
        c2 = tf.constant(np.random.random((10, 10)))
        c3 = tf.constant(np.random.random((10, 20)))
        result = sess.run(adaptive.compute_logprob([c1, c2, c3], [10, 20, 40]))
        # did we get the right shape?
        assert (10, 40) == result.shape
        # do we have a valid probability distribution?
        prob_sum = np.sum(np.exp(result), axis=-1)
        assert np.all((prob_sum > 0.99999) & (prob_sum < 1.00001))

def test_AdaptiveSoftmaxProduceLogits_2d_inputs():
    vocab_size=10000
    cutoffs = [5000, 7000, 10000]

    data_input = Input(shape=(1000,), dtype='float32')
    labels_input = Input(shape=(1,), dtype='int32')
    adaptive_softmax = adaptive.AdaptiveSoftmaxProduceLogits(vocab_size, cutoffs=cutoffs)
    adaptive_softmax_out = adaptive_softmax([data_input, labels_input])

    # verify kernels for each cluster have correct dimensions
    assert (1000, 5002) == adaptive_softmax.cluster_kernels[0].shape
    assert (250, 2000) == adaptive_softmax.cluster_kernels[1].shape
    assert (62, 3000) == adaptive_softmax.cluster_kernels[2].shape

    # verify bais matrices have correct dimensions
    assert (5002,) == adaptive_softmax.cluster_biases[0].shape
    assert (2000,) == adaptive_softmax.cluster_biases[1].shape
    assert (3000,) == adaptive_softmax.cluster_biases[2].shape

    # verify projection matrices have correct dimensions
    assert adaptive_softmax.cluster_projections[0] is None
    assert (1000, 250) == adaptive_softmax.cluster_projections[1].shape
    assert (1000, 62) == adaptive_softmax.cluster_projections[2].shape

    retrieve_adaptive_softmax_output = K.function(
        [data_input, labels_input],
        adaptive_softmax_out)

    X = np.ones((10, 1000)).astype('float32')
    labels = np.array([[5842],
                       [2091],
                       [9793],
                       [8083],
                       [1473],
                       [3982],
                       [2364],
                       [8102],
                       [377],
                       [5615]]).astype('int32')
    outputs = retrieve_adaptive_softmax_output([X, labels])

    # verify the output shapes
    assert len(outputs) == len(cutoffs)
    assert (labels.shape[0], 5002) == outputs[0].shape
    assert (labels.shape[0], 2000) == outputs[1].shape
    assert (labels.shape[0], 3000) == outputs[2].shape

def test_AdaptiveSoftmaxProduceLogits_3d_inputs():
    vocab_size=10000
    cutoffs = [5000, 7000, 10000]

    data_input = Input(shape=(None,1000), dtype='float32')
    labels_input = Input(shape=(None,1), dtype='int32')
    adaptive_softmax = adaptive.AdaptiveSoftmaxProduceLogits(vocab_size, cutoffs=cutoffs)
    adaptive_softmax_out = adaptive_softmax([data_input, labels_input])

    retrieve_adaptive_softmax_output = K.function(
        [data_input, labels_input],
        adaptive_softmax_out)

    X = np.ones((10, 5, 1000)).astype('float32')
    labels = np.array([[5586, 3971, 7741, 1349, 2822],
                       [3422, 1215, 6291, 7520, 1730],
                       [8577, 2887, 1507, 9086, 2399],
                       [4154, 7241, 1640, 3606, 9889],
                       [6227, 6129,  637, 8587, 1059],
                       [5079, 1630, 8016, 5110, 1078],
                       [2296, 1792, 7380, 1217, 3860],
                       [5159,  681, 8546, 2018, 5645],
                       [ 506, 3150, 6184, 6312, 2690],
                       [ 448,  982, 5918, 1128, 3960]], dtype='int32')
    labels = np.expand_dims(labels, axis=-1)
    outputs = retrieve_adaptive_softmax_output([X, labels])

    # verify the output shapes
    assert len(outputs) == len(cutoffs)
    assert (labels.shape[0], 5, 5002) == outputs[0].shape
    assert (labels.shape[0], 5, 2000) == outputs[1].shape
    assert (labels.shape[0], 5, 3000) == outputs[2].shape

def test_AdaptiveSoftmaxProduceLogits_masking():
    vocab_size=10000
    cutoffs = [5000, 7000, 10000]

    data_input = Input(shape=(5,1000), dtype='float32')
    labels_input = Input(shape=(5,1), dtype='int32')
    mask = tf.constant([[True,  True,  True,  True,  False],
                        [True,  True,  False, False, False],
                        [True,  True,  True,  True,  False],
                        [True,  True,  True,  False, False],
                        [True,  True,  True,  True,  False],
                        [True,  True,  True,  True,   True],
                        [True,  True,  True,  True,   True],
                        [True,  True,  True,  True,   True],
                        [True,  False, False, False, False],
                        [True,  True,  True,  True,  False]])
    add_mask = Lambda(lambda x: x, mask=[mask, mask])
    inputs_masked = add_mask([data_input, labels_input])

    adaptive_softmax = adaptive.AdaptiveSoftmaxProduceLogits(vocab_size, cutoffs=cutoffs)
    adaptive_softmax_out = adaptive_softmax(inputs_masked)

    retrieve_adaptive_softmax_output = K.function(
        [data_input, labels_input],
        adaptive_softmax_out)

    X = np.ones((10, 5, 1000)).astype('float32')
    labels = np.array([[5586, 3971, 7741, 1349, 2822],
                       [3422, 1215, 6291, 7520, 1730],
                       [8577, 2887, 1507, 9086, 2399],
                       [4154, 7241, 1640, 3606, 9889],
                       [6227, 6129,  637, 8587, 1059],
                       [5079, 1630, 8016, 5110, 1078],
                       [2296, 1792, 7380, 1217, 3860],
                       [5159,  681, 8546, 2018, 5645],
                       [ 506, 3150, 6184, 6312, 2690],
                       [ 448,  982, 5918, 1128, 3960]], dtype='int32')
    labels = np.expand_dims(labels, axis=-1)
    outputs = retrieve_adaptive_softmax_output([X, labels])

    # verify the output shapes
    assert len(outputs) == len(cutoffs)
    assert (10, 5, 5002) == outputs[0].shape
    assert (10, 5, 2000) == outputs[1].shape
    assert (10, 5, 3000) == outputs[2].shape

def test_AdaptiveSoftmaxProduceLogits_masking_cost():
    data_input = Input(shape=(20,), dtype='int32')
    labels_input = Input(shape=(20,1), dtype='int32')

    embedding_layer = Embedding(
        11,
        6,
        mask_zero=True,
        embeddings_initializer=initializers.Constant(value=0.1))

    # By setting the weight values to a 0.1, we ensure that labels in a child
    # cluster will always have lower probability that those in the head. We
    # exploit this fact to check if masking is handled correctly.
    logits_layer = adaptive.AdaptiveSoftmaxProduceLogits(
        10,
        cutoffs=[5],
        kernel_initializer=initializers.Constant(value=0.1),
        projection_initializer=initializers.Constant(value=0.1))

    x = embedding_layer(data_input)
    x = logits_layer([x, labels_input])

    model = Model(inputs=[data_input, labels_input], outputs=x)
    model.compile(optimizer='adam')

    # Create random dataset where each sample has a different length with 0 padding
    # and none of the labels use category 1
    x_data = np.zeros((32, 20))
    y_data = np.zeros((32, 20, 1))
    for i in range(32):
        length = np.random.randint(1, 20)
        x_data[i, 0:length] = np.random.randint(2, 5, size=length)
        y_data[i, 0:length] = np.random.randint(2, 5, size=(length, 1))

    # Evaluate to get the cost
    cost1 = model.evaluate([x_data, y_data])

    # Change the 0s to 7s in the labels. If masking is handled correctly, this
    # shouldn't matter as these labels will be ignored anyway. If masking is not
    # handled correctly, then the cost should go up as the probability of 7
    # being the correct category is lower than categories 1-5.
    y_data[y_data == 0] = 7

    cost2 = model.evaluate([x_data, y_data])

    assert cost1 == cost2

def test_AdaptiveLogProb():
    vocab_size=10000
    cutoffs = [5000, 7000, 10000]

    data_input = Input(shape=(None,1000), dtype='float32')

    x = adaptive.AdaptiveSoftmaxProduceLogits(vocab_size, cutoffs=cutoffs)(data_input)
    x = adaptive.AdaptiveLogProb()(x)

    retrieve_adaptive_softmax_output = K.function([data_input], [x])

    outputs = retrieve_adaptive_softmax_output([np.random.random((2, 5, 1000)).astype('float32')])
    prob_sum = np.sum(np.exp(outputs), axis=-1)
    assert np.all((prob_sum > 0.99999) & (prob_sum < 1.00001))

def test_AdaptiveProb():
    vocab_size=10000
    cutoffs = [5000, 7000, 10000]

    data_input = Input(shape=(None,1000), dtype='float32')

    x = adaptive.AdaptiveSoftmaxProduceLogits(vocab_size, cutoffs=cutoffs)(data_input)
    x = adaptive.AdaptiveProb()(x)

    retrieve_adaptive_softmax_output = K.function([data_input], [x])

    outputs = retrieve_adaptive_softmax_output([np.random.random((2, 5, 1000)).astype('float32')])
    prob_sum = np.sum(outputs, axis=-1)
    assert np.all((prob_sum > 0.999) & (prob_sum < 1.001))
