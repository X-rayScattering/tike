"""Implement cost functions and gradients."""

import cupy as cp

# NOTE: We use mean instead of sum so that cost functions may be compared
# when mini-batches of different sizes are used.

# Gaussian Model


@cp.fuse()
def _gaussian_fuse(data, intensity):
    diff = cp.sqrt(intensity) - cp.sqrt(data)
    diff *= cp.conj(diff)
    return diff


def gaussian(data, intensity) -> float:
    """The Gaussian model objective function.

    Parameters
    ----------
    data : (N, M, M)
        The measured diffraction data
    intensity : (N, M, M)
        The modeled intensity
    """
    return cp.mean(_gaussian_fuse(data, intensity))


cp.fuse()
def gaussian_grad(data, farplane, intensity) -> cp.ndarray:
    """The gradient of the Gaussian model objective function

    Parameters
    ----------
    data : (N, M, M)
        The measured diffraction data
    intensity : (N, M, M)
        The modeled intensity
    farplane : (N, K, L, M, M)
    """
    return farplane * (1 - cp.sqrt(data) /
                       (cp.sqrt(intensity) + 1e-9))[..., cp.newaxis,
                                                    cp.newaxis, :, :]


def gaussian_each_pattern(data, intensity) -> cp.ndarray:
    """The Gaussian model objective function per diffraction pattern.

    Parameters
    ----------
    data : (N, M, M)
        The measured diffraction data
    intensity : (N, M, M)
        The modeled intensity

    Returns
    -------
    costs : (N, )
        The objective function for each pattern.
    """
    return cp.mean(
        _gaussian_fuse(data, intensity),
        axis=(-2, -1),
        keepdims=False,
    )


# Poisson Model


@cp.fuse()
def _poisson_fuse(data, intensity):
    return intensity - data * cp.log(intensity + 1e-9)


def poisson(data, intensity) -> float:
    """The Poisson model objective function.

    Parameters
    ----------
    data : (N, M, M)
        The measured diffraction data
    intensity : (N, M, M)
        The modeled intensity
    """
    return cp.mean(_poisson_fuse(data, intensity))


cp.fuse()
def poisson_grad(data, farplane, intensity) -> cp.ndarray:
    """The gradient of the Poisson model objective function.

    Parameters
    ----------
    data : (N, M, M)
        The measured diffraction data
    intensity : (N, M, M)
        The modeled intensity
    farplane : (N, K, L, M, M)
    """
    return farplane * (1 - data /
                       (intensity + 1e-9))[..., cp.newaxis, cp.newaxis, :, :]


def poisson_each_pattern(data, intensity) -> cp.ndarray:
    """The Poisson model objective function per diffraction pattern.

    Parameters
    ----------
    data : (N, M, M)
        The measured diffraction data
    intensity : (N, M, M)
        The modeled intensity

    Returns
    -------
    costs : (N, )
        The objective function for each pattern.
    """
    return cp.mean(
        _poisson_fuse(data, intensity),
        axis=(-2, -1),
        keepdims=False,
    )
