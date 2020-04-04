import tensorflow as tf
import lidbox.features as features
import lidbox.features.audio as audio_features


def tf_print(*args, **kwargs):
    if "summarize" not in kwargs:
        kwargs["summarize"] = -1
    if "output_stream" not in kwargs:
        kwargs["output_stream"] = sys.stdout
    return tf.print(*args, **kwargs)


def count_dim_sizes(ds, ds_element_index=0, ndims=1):
    """
    Given a dataset 'ds' of 'ndims' dimensional tensors at element index 'ds_element_index', accumulate the shape counts of all tensors.
    >>> batch, x, y = 10, 3, 4
    >>> data = tf.random.normal((batch, x, y))
    >>> meta = tf.random.normal((batch, 1))
    >>> ds = tf.data.Dataset.from_tensor_slices((data, meta))
    >>> data_sizes = count_dim_sizes(ds, 0, 2)
    >>> x_size = tf.squeeze(data_sizes[0], 0)
    >>> tf.math.reduce_all(x_size == [batch, x]).numpy()
    True
    >>> y_size = tf.squeeze(data_sizes[1], 0)
    >>> tf.math.reduce_all(y_size == [batch, y]).numpy()
    True
    >>> meta_size = tf.squeeze(count_dim_sizes(ds, 1, 1), [0, 1])
    >>> tf.math.reduce_all(meta_size == [batch, 1]).numpy()
    True
    """
    tf.debugging.assert_greater(ndims, 0)
    get_shape_at_index = lambda *t: tf.shape(t[ds_element_index])
    shapes_ds = ds.map(get_shape_at_index)
    ones = tf.ones(ndims, dtype=tf.int32)
    shape_indices = tf.range(ndims, dtype=tf.int32)
    def accumulate_dim_size_counts(counter, shape):
        enumerated_shape = tf.stack((shape_indices, shape), axis=1)
        return tf.tensor_scatter_nd_add(counter, enumerated_shape, ones)
    max_sizes = shapes_ds.reduce(
        tf.zeros(ndims, dtype=tf.int32),
        lambda acc, shape: tf.math.maximum(acc, shape))
    max_max_size = tf.math.reduce_max(max_sizes)
    size_counts = shapes_ds.reduce(
        tf.zeros((ndims, max_max_size + 1), dtype=tf.int32),
        accumulate_dim_size_counts)
    sorted_size_indices = tf.argsort(size_counts, direction="DESCENDING")
    sorted_size_counts = tf.gather(size_counts, sorted_size_indices, batch_dims=1)
    is_nonzero = sorted_size_counts > 0
    return tf.ragged.stack(
        (tf.ragged.boolean_mask(sorted_size_counts, is_nonzero),
         tf.ragged.boolean_mask(sorted_size_indices, is_nonzero)),
        axis=2)


def make_label2onehot(labels):
    """
    >>> labels = tf.constant(["one", "two", "three"], tf.string)
    >>> label2int, OH = make_label2onehot(labels)
    >>> for i in range(3):
    ...     (label2int.lookup(labels[i]).numpy(), tf.math.argmax(OH[i]).numpy())
    (0, 0)
    (1, 1)
    (2, 2)
    """
    labels_enum = tf.range(len(labels))
    # Label to int or one past last one if not found
    # TODO slice index out of bounds is probably not a very informative error message
    label2int = tf.lookup.StaticHashTable(
        tf.lookup.KeyValueTensorInitializer(
            tf.constant(labels),
            tf.constant(labels_enum)
        ),
        tf.constant(len(labels), dtype=tf.int32)
    )
    OH = tf.one_hot(labels_enum, len(labels))
    return label2int, OH


def extract_features(signals, sample_rates, feattype, spec_kwargs, melspec_kwargs, mfcc_kwargs, db_spec_kwargs, feat_scale_kwargs, window_norm_kwargs):
    tf.debugging.assert_rank(signals, 2, message="Input signals for feature extraction must be batches of mono signals without channels, i.e. of shape [B, N] where B is batch size and N number of samples.")
    tf.debugging.assert_equal(sample_rates, [sample_rates[0]], message="Different sample rates in a single batch not supported, all signals in the same batch should have the same sample rate.")
    #TODO batches with different sample rates (probably not worth the effort)
    sample_rate = sample_rates[0]
    feat = audio_features.spectrograms(signals, sample_rate, **spec_kwargs)
    # tf.debugging.assert_all_finite(feat, "spectrogram failed")
    if feattype in ("melspectrogram", "logmelspectrogram", "mfcc"):
        feat = audio_features.melspectrograms(feat, sample_rate=sample_rate, **melspec_kwargs)
        # tf.debugging.assert_all_finite(feat, "melspectrogram failed")
        if feattype in ("logmelspectrogram", "mfcc"):
            feat = tf.math.log(feat + 1e-6)
            # tf.debugging.assert_all_finite(feat, "logmelspectrogram failed")
            if feattype == "mfcc":
                coef_begin = mfcc_kwargs.get("coef_begin", 1)
                coef_end = mfcc_kwargs.get("coef_end", 13)
                mfccs = tf.signal.mfccs_from_log_mel_spectrograms(feat)
                feat = mfccs[..., coef_begin:coef_end]
                # tf.debugging.assert_all_finite(feat, "mfcc failed")
    elif feattype in ("db_spectrogram",):
        feat = audio_features.power_to_db(feat, **db_spec_kwargs)
        # tf.debugging.assert_all_finite(feat, "db_spectrogram failed")
    if feat_scale_kwargs:
        feat = features.feature_scaling(feat, **feat_scale_kwargs)
        # tf.debugging.assert_all_finite(feat, "feature scaling failed")
    if window_norm_kwargs:
        feat = features.window_normalization(feat, **window_norm_kwargs)
        # tf.debugging.assert_all_finite(feat, "window normalization failed")
    tf.debugging.assert_all_finite(feat, "Non-finite values after feature extraction")
    return feat


#TODO
# for conf in augment_config:
#     # prepare noise augmentation
#     if conf["type"] == "additive_noise":
#         noise_source_dir = conf["noise_source"]
#         conf["noise_source"] = {}
#         with open(os.path.join(noise_source_dir, "id2label")) as f:
#             id2label = dict(l.strip().split() for l in f)
#         label2path = collections.defaultdict(list)
#         with open(os.path.join(noise_source_dir, "id2path")) as f:
#             for noise_id, path in (l.strip().split() for l in f):
#                 label2path[id2label[noise_id]].append((noise_id, path))
#         tmpdir = conf.get("copy_to_tmpdir")
#         if tmpdir:
#             if os.path.isdir(tmpdir):
#                 if verbosity:
#                     print("tmpdir for noise source files given, but it already exists at '{}', so copying will be skipped".format(tmpdir))
#             else:
#                 if verbosity:
#                     print("copying all noise source wavs to '{}'".format(tmpdir))
#                 os.makedirs(tmpdir)
#                 tmp = collections.defaultdict(list)
#                 for noise_type, noise_paths in label2path.items():
#                     for noise_id, path in noise_paths:
#                         new_path = os.path.join(tmpdir, noise_id + ".wav")
#                         shutil.copy2(path, new_path)
#                         if verbosity > 3:
#                             print(" ", path, "->", new_path)
#                         tmp[noise_type].append((noise_id, new_path))
#                 label2path = tmp
#         for noise_type, noise_paths in label2path.items():
#             conf["noise_source"][noise_type] = [path for _, path in noise_paths]
# def chunk_loader(signal, sr, meta, *args):
#     chunk_length = int(sr * chunk_len_seconds)
#     max_pad = int(sr * max_pad_seconds)
#     if signal.size + max_pad < chunk_length:
#         if verbosity:
#             tf_util.tf_print("skipping too short signal (min chunk length is ", chunk_length, " + ", max_pad, " max_pad): length ", signal.size, ", utt ", meta[0], output_stream=sys.stderr, sep='')
#         return
#     uttid = meta[0].decode("utf-8")
#     yield from chunker(signal, target_sr, (uttid, *meta[1:]))
#     rng = np.random.default_rng()
#     for conf in augment_config:
#         if conf["type"] == "random_resampling":
#             # apply naive speed modification by resampling
#             ratio = rng.uniform(conf["range"][0], conf["range"][1])
#             with contextlib.closing(io.BytesIO()) as buf:
#                 soundfile.write(buf, signal, int(ratio * target_sr), format="WAV")
#                 buf.seek(0)
#                 resampled_signal, _ = librosa.core.load(buf, sr=target_sr, mono=True)
#             new_uttid = "{:s}-speed{:.3f}".format(uttid, ratio)
#             new_meta = (new_uttid, *meta[1:])
#             yield from chunker(resampled_signal, target_sr, new_meta)
#         elif conf["type"] == "additive_noise":
#             for noise_type, db_min, db_max in conf["snr_def"]:
#                 noise_signal = np.zeros(0, dtype=signal.dtype)
#                 noise_paths = []
#                 while noise_signal.size < signal.size:
#                     rand_noise_path = rng.choice(conf["noise_source"][noise_type])
#                     noise_paths.append(rand_noise_path)
#                     sig, _ = librosa.core.load(rand_noise_path, sr=target_sr, mono=True)
#                     noise_signal = np.concatenate((noise_signal, sig))
#                 noise_begin = rng.integers(0, noise_signal.size - signal.size, endpoint=True)
#                 noise_signal = noise_signal[noise_begin:noise_begin+signal.size]
#                 snr_db = rng.integers(db_min, db_max, endpoint=True)
#                 clean_and_noise = audio_feat.numpy_snr_mixer(signal, noise_signal, snr_db)[2]
#                 new_uttid = "{:s}-{:s}_snr{:d}".format(uttid, noise_type, snr_db)
#                 if not np.all(np.isfinite(clean_and_noise)):
#                     if verbosity:
#                         tf_util.tf_print("warning: snr_mixer failed, augmented signal ", new_uttid, " has non-finite values and will be skipped. Utterance was ", uttid, ", and chosen noise signals were\n  ", tf.strings.join(noise_paths, separator="\n  "), output_stream=sys.stderr, sep='')
#                     return
#                 new_meta = (new_uttid, *meta[1:])
#                 yield from chunker(clean_and_noise, target_sr, new_meta)
