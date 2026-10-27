# -*- coding: utf-8 -*-


def post_init(env):
    """Post-install hook: ensure there is an `avicola.veterinario` record
    for each user that already belongs to the `gestion_avicola.group_veterinario` group.
    """
    try:
        group = env.ref('gestion_avicola.group_veterinario', raise_if_not_found=False)
    except Exception:
        group = None
    if not group:
        return
    users = env['res.users'].search([('group_ids', 'in', group.id)])
    for user in users:
        vet = env['avicola.veterinario'].search([('user_id', '=', user.id)], limit=1)
        if not vet:
            env['avicola.veterinario'].create({
                'user_id': user.id,
                'name': user.name or user.login,
            })
