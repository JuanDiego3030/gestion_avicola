# -*- coding: utf-8 -*-


def post_init(*args, **kwargs):
    """Post-install hook: ensure there is an `avicola.veterinario` record
    for each user that already belongs to the `gestion_avicola.group_veterinario` group.
    """
    if len(args) == 1:
        env = args[0]
    elif len(args) >= 2:
        from odoo import api, SUPERUSER_ID
        env = api.Environment(args[0], SUPERUSER_ID, {})
    else:
        env = kwargs.get('env')
    try:
        group = env.ref('gestion_avicola.group_veterinario', raise_if_not_found=False)
    except Exception:
        group = None
    if not group:
        return
    field_name = 'group_ids' if 'group_ids' in env['res.users']._fields else 'groups_id'
    users = env['res.users'].search([(field_name, 'in', group.id)])
    for user in users:
        vet = env['avicola.veterinario'].search([('user_id', '=', user.id)], limit=1)
        if not vet:
            env['avicola.veterinario'].create({
                'user_id': user.id,
                'name': user.name or user.login,
            })
