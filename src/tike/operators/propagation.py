"""Defines a free-space propagation operator based on the NumPy FFT module."""

import numpy as np

from .operator import Operator


class Propagation(Operator):
    """A base class for Fourier-based free-space propagation."""

    def __init__(self, nwaves, detector_shape, probe_shape, model='gaussian',
                 **kwargs):  # yapf: disable
        self.nwaves = nwaves
        self.probe_shape = probe_shape
        self.detector_shape = detector_shape
        self.cost = getattr(self, f'_{model}_cost')
        self.grad = getattr(self, f'_{model}_grad')

    def fwd(self, nearplane, **kwargs):
        """Forward Fourier-based free-space propagation operator."""
        assert self.nwaves == np.prod(nearplane.shape[:-2])
        # We must cast the result of np.fft.fft2
        # because this implementation does not preserve type.
        return np.fft.fft2(
            nearplane,
            norm='ortho',
        ).astype('complex64')

    def adj(self, farplane, **kwargs):
        """Adjoint Fourier-based free-space propagation operator."""
        assert self.nwaves == np.prod(farplane.shape[:-2])
        return np.fft.ifft2(
            farplane,
            norm='ortho',
        ).astype('complex64')

    # COST FUNCTIONS AND GRADIENTS --------------------------------------------

    def _gaussian_cost(self, data, farplane):
        modulus = np.linalg.norm(
            farplane.reshape(*data.shape[:2], -1, *data.shape[2:]),
            ord=2,
            axis=2,
        )
        return np.linalg.norm(np.ravel(modulus - np.sqrt(data)))**2

    def _gaussian_grad(self, data, farplane, overwrite=False):
        modulus = np.linalg.norm(
            farplane.reshape(*data.shape[:2], -1, *data.shape[2:]),
            ord=2,
            axis=2,
        )
        return farplane * (
            1 - np.sqrt(data) / (modulus + 1e-32)
        )[:, :, np.newaxis, np.newaxis]  # yapf:disable

    def _poisson_cost(self, data, farplane):
        intensity = np.square(np.linalg.norm(
            farplane.reshape(*data.shape[:2], -1, *data.shape[2:]),
            ord=2,
            axis=2,
        ))
        return np.sum(intensity - data * np.log(intensity + 1e-32))

    def _poisson_grad(self, data, farplane, overwrite=False):
        intensity = np.square(np.linalg.norm(
            farplane.reshape(*data.shape[:2], -1, *data.shape[2:]),
            ord=2,
            axis=2,
        ))
        return farplane * (
            1 - data / (intensity + 1e-32)
        )[:, :, np.newaxis, np.newaxis]  # yapf: disable
