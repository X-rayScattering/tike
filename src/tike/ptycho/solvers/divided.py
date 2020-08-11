import logging

from tike.opt import conjugate_gradient, line_search, direction_dy
from ..position import update_positions_pd

logger = logging.getLogger(__name__)


def divided(
    op, pool, num_gpu,
    data, probe, scan, psi,
    recover_psi=True, recover_probe=False, recover_positions=False,
    cg_iter=4,
    **kwargs
):  # yapf: disable
    """Solve near- and farfield- ptychography problems separately.

    References
    ----------
    Michal Odstrcil, Andreas Menzel, and Manuel Guizar-Sicaros. Iteraive
    least-squares solver for generalized maximum-likelihood ptychography.
    Optics Express. 2018.

    """
    farplane = op.fwd(psi=psi, scan=scan, probe=probe)
    farplane, cost = update_phase(op, data, farplane, num_iter=cg_iter)
    nearplane = op.propagation.adj(farplane)
    if recover_psi:
        psi, cost = update_object(
            op,
            nearplane,
            probe,
            scan,
            psi,
            num_iter=cg_iter,
        )
    if recover_probe:
        probe, cost = update_probe(
            op,
            nearplane,
            probe,
            scan,
            psi,
            num_iter=cg_iter,
        )
    # if recover_positions:
    #     scan, cost = update_positions_pd(op, data, psi, probe, scan)
    return {
        'psi': psi,
        'probe': probe,
        'cost': cost,
        'scan': scan,
        'farplane': farplane,
    }


def update_phase(op, data, farplane, num_iter=1):
    """Solve the farplane phase problem."""

    def grad(farplane):
        intensity = op.xp.square(op.xp.abs(farplane))[:, :, 0, 0]
        return op.propagation.grad(data, farplane, intensity)

    def cost_function(farplane):
        intensity = op.xp.square(op.xp.abs(farplane))[:, :, 0, 0]
        return op.propagation.cost(data, intensity)

    farplane, cost = conjugate_gradient(
        op.xp,
        x=farplane,
        cost_function=cost_function,
        grad=grad,
        num_iter=num_iter,
    )

    # print cost function for sanity check
    logger.info('%10s cost is %+12.5e', 'farplane', cost)
    return farplane, cost


def update_probe(
    op,
    nearplane,
    probe,
    scan,
    psi,
    num_iter=1,
    position=1,
    eps=1e-16,
    pixels=(-1, -2),
):
    """Solve the nearplane single probe recovery problem."""
    xp = op.xp
    pad, end = op.diffraction.pad, op.diffraction.end
    obj_patches = op.diffraction._patch(
        patches=xp.zeros(
            shape=(*scan.shape[:2], 1, 1, *probe.shape[-2:]),
            dtype='complex64',
        ),
        psi=psi,
        scan=scan,
        fwd=True,
    )

    norm_patches = xp.sum(
        xp.square(xp.abs(obj_patches)),
        axis=position,
        keepdims=True,
    ) + eps

    def cost_function(probe):
        return xp.linalg.norm(
            xp.ravel(probe * obj_patches - nearplane[..., pad:end, pad:end]))**2

    def chi(probe):
        return nearplane[..., pad:end, pad:end] - probe * obj_patches

    def grad(probe):
        return chi(probe) * xp.conj(obj_patches)

    def common_dir_(dir_):
        return xp.sum(dir_, axis=position, keepdims=True) / norm_patches

    def step(probe, dir_):
        return xp.sum(
            xp.real(chi(probe) * xp.conj(dir_ * obj_patches)),
            axis=pixels,
            keepdims=True,
        ) / (xp.sum(
            xp.square(xp.abs(dir_ * obj_patches)),
            axis=pixels,
            keepdims=True,
        ) + eps)

    for i in range(num_iter):
        grad1 = grad(probe)
        if i == 0:
            dir_ = -grad1
        else:
            dir_ = direction_dy(xp, grad0, grad1, dir_)
        grad0 = grad1

        weighted_patches = xp.sum(
            step(probe, dir_) * xp.square(xp.abs(obj_patches)),
            axis=position,
            keepdims=True,
        )

        probe = probe + common_dir_(dir_) * weighted_patches / norm_patches

    cost = cost_function(probe)
    logger.info('%10s cost is %+12.5e', 'probe', cost)
    return probe, cost


def update_object(
    op,
    nearplane,
    probe,
    scan,
    psi,
    num_iter=1,
    position=1,
    eps=1e-16,
    pixels=(-1, -2),
):
    """Solve the nearplane object recovery problem."""
    xp = op.xp
    pad, end = op.diffraction.pad, op.diffraction.end

    def cost_function(psi):
        return xp.linalg.norm(
            xp.ravel(
                op.diffraction.fwd(psi=psi, scan=scan, probe=probe) -
                nearplane))**2

    def chi(psi):
        return (nearplane -
                op.diffraction.fwd(psi=psi, scan=scan, probe=probe))[...,
                                                                     pad:end,
                                                                     pad:end]

    def grad(psi):
        return chi(psi) * xp.conj(probe)

    norm_probe = op.diffraction._patch(
        patches=xp.square(xp.abs(probe)) * xp.ones(
            (*scan.shape[:2], 1, 1, 1, 1),
            dtype='complex64',
        ),
        psi=xp.zeros_like(psi),
        scan=scan,
        fwd=False,
    ) + eps

    def common_dir_(dir_):
        return op.diffraction._patch(
            patches=dir_,
            scan=scan,
            psi=xp.zeros_like(psi),
            fwd=False,
        ) / norm_probe

    def step(psi, dir_):
        # TODO: Figure out if steps should be complex instead of real
        result = xp.sum(
            xp.real(chi(psi) * xp.conj(dir_ * probe)),
            axis=pixels,
            keepdims=True,
        ) / (xp.sum(
            xp.square(xp.abs(dir_ * probe)),
            axis=pixels,
            keepdims=True,
        ) + eps)
        return result

    for i in range(num_iter):
        grad1 = grad(psi)
        if i == 0:
            dir_ = -grad1
        else:
            dir_ = direction_dy(xp, grad0, grad1, dir_)
        grad0 = grad1

        weight_probe = op.diffraction._patch(
            patches=(step(psi, dir_) *
                     xp.square(xp.abs(probe))).astype('complex64'),
            psi=xp.zeros_like(psi),
            scan=scan,
            fwd=False,
        )
        psi = psi + common_dir_(dir_) * weight_probe / norm_probe

    cost = cost_function(psi)
    logger.info('%10s cost is %+12.5e', 'object', cost)
    return psi, cost