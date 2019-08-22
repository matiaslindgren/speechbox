import collections

import librosa
import numpy as np


def extract_features(utterance_wav, extractor, config):
    assert isinstance(utterance_wav, tuple) and len(utterance_wav) == 2, "Expected utterance as a (signal, sample_rate) tuple, but got type '{}'".format(type(utterance_wav))
    extractor_func = all_extractors[extractor]
    features = extractor_func(utterance_wav, **config)
    assert features.ndim == 2, "Unexpected dimension {} for features, expected 2".format(features.ndim)
    return features

def mfcc(utterance, normalize=False, mel_spec_power=1.0, **kwargs):
    """
    MFCCs and normalize each coef by L2 norm.
    """
    signal, rate = utterance
    # Extract MFCCs
    S = librosa.feature.melspectrogram(y=signal, sr=rate)
    S = librosa.power_to_db(S**mel_spec_power, ref=np.max)
    mfccs = librosa.feature.mfcc(y=signal, sr=rate, S=S, **kwargs)
    # Normalize each coefficient such that the L2 norm for each coefficient over all frames is equal to 1
    if normalize:
        mfccs = librosa.util.normalize(mfccs, norm=2.0, axis=0)
    return mfccs.T

def mfcc_deltas_012(utterance, **kwargs):
    """
    MFCCs, normalize each coef by L2 norm, compute 1st and 2nd order deltas on MFCCs and append them to the "0th order delta".
    Return an array of (0th, 1st, 2nd) deltas for each sample in utterance.
    """
    mfccs = mfcc(utterance, **kwargs).T
    # Compute deltas and delta-deltas and interleave them for every frame
    # i.e. for frames f_i, the features are:
    # f_0, d(f_0), d(d(f_0)), f_1, d(f_1), d(d(f_1)), f_2, d(f_2), ...
    features = np.empty((3 * mfccs.shape[0], mfccs.shape[1]), dtype=mfccs.dtype)
    features[0::3] = mfccs
    features[1::3] = librosa.feature.delta(mfccs, order=1, width=3)
    features[2::3] = librosa.feature.delta(mfccs, order=2, width=5)
    return features.T


all_extractors = collections.OrderedDict([
    ("mfcc", mfcc),
    ("mfcc-deltas-012", mfcc_deltas_012),
])
