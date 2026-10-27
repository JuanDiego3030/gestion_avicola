# -*- coding: utf-8 -*-
import logging
from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AvicolaGranja(models.Model):
    _name = 'avicola.granja'
    _description = 'Granja de Engorde'
    _order = 'name'

    name = fields.Char(string='Nombre', required=True)
    tipo = fields.Selection(
        [('propia', 'Propia'), ('alquilada', 'Alquilada')],
        string='Tipo', required=True, default='propia'
    )
    ubicacion = fields.Char(string='Ubicación')
    galpon_ids = fields.One2many('avicola.galpon', 'granja_id', string='Galpones')
    total_galpones = fields.Integer(string='Total Galpones', compute='_compute_totals', store=True)
    total_aves = fields.Integer(string='Población Total (Aves)', compute='_compute_totals', store=True)
    metros_totales = fields.Float(string='Superficie Total (m²)', compute='_compute_totals', store=True, digits=(10, 2))

    @api.depends('galpon_ids', 'galpon_ids.cantidad_actual', 'galpon_ids.metros_cuadrados')
    def _compute_totals(self):
        for rec in self:
            rec.total_galpones = len(rec.galpon_ids)
            rec.total_aves = sum(rec.galpon_ids.mapped('cantidad_actual'))
            rec.metros_totales = sum(rec.galpon_ids.mapped('metros_cuadrados'))


class AvicolaGalpon(models.Model):
    _name = 'avicola.galpon'
    _description = 'Galpón'
    _order = 'granja_id, name'

    granja_id = fields.Many2one('avicola.granja', string='Granja', required=True, ondelete='cascade')
    name = fields.Char(string='Nombre', required=True)
    metros_cuadrados = fields.Float(string='Metros Cuadrados', digits=(10, 2), default=0.0)
    capacidad_maxima = fields.Integer(string='Capacidad Máxima', default=0)
    cantidad_actual = fields.Integer(string='Cantidad Actual de Aves', default=0)
    densidad_actual = fields.Float(
        string='Densidad Actual (aves/m²)',
        compute='_compute_densidad_actual',
        store=True,
        digits=(10, 2),
    )
    mortalidad_ids = fields.One2many('avicola.mortalidad', 'galpon_id', string='Mortalidad')
    total_mortalidad = fields.Integer(
        string='Total Mortalidad',
        compute='_compute_total_mortalidad',
        store=True,
    )

    @api.depends('cantidad_actual', 'metros_cuadrados')
    def _compute_densidad_actual(self):
        for rec in self:
            if rec.metros_cuadrados and rec.metros_cuadrados > 0:
                rec.densidad_actual = rec.cantidad_actual / rec.metros_cuadrados
            else:
                rec.densidad_actual = 0.0

    @api.depends('mortalidad_ids.cantidad')
    def _compute_total_mortalidad(self):
        for rec in self:
            rec.total_mortalidad = sum(rec.mortalidad_ids.mapped('cantidad'))


class AvicolaDistribucion(models.Model):
    _name = 'avicola.distribucion'
    _description = 'Distribución de Pollitos'
    _order = 'fecha desc, id desc'

    lote_incubadora = fields.Char(string='Lote Incubadora', required=True)
    fecha = fields.Date(string='Fecha', required=True, default=fields.Date.today)
    granja_id = fields.Many2one('avicola.granja', string='Granja', required=True)
    galpon_id = fields.Many2one(
        'avicola.galpon', string='Galpón', required=True,
        domain="[('granja_id', '=', granja_id)]"
    )
    cantidad = fields.Integer(string='Cantidad', required=True)
    estado = fields.Selection(
        [('borrador', 'Borrador'), ('confirmado', 'Confirmado')],
        string='Estado', default='borrador', required=True
    )

    def action_confirmar(self):
        for rec in self:
            if rec.estado == 'confirmado':
                raise UserError('Este registro ya está confirmado.')
            if not rec.galpon_id:
                raise UserError('Debe seleccionar un galpón.')
            if rec.cantidad <= 0:
                raise UserError('La cantidad de pollitos debe ser mayor a cero.')
            rec.galpon_id.cantidad_actual += rec.cantidad
            rec.estado = 'confirmado'

    def action_borrador(self):
        for rec in self:
            if rec.estado == 'confirmado':
                if rec.galpon_id.cantidad_actual < rec.cantidad:
                    raise UserError(
                        f'No se puede revertir: la cantidad actual en el galpón ({rec.galpon_id.cantidad_actual}) '
                        f'es menor que la cantidad distribuida ({rec.cantidad}).'
                    )
                rec.galpon_id.cantidad_actual -= rec.cantidad
            rec.estado = 'borrador'


class AvicolaMortalidad(models.Model):
    _name = 'avicola.mortalidad'
    _description = 'Registro de Mortalidad de Aves'
    _order = 'fecha desc, id desc'

    lote_incubadora = fields.Char(
        string='Lote Incubadora',
        compute='_compute_lote_incubadora',
        store=True,
        readonly=False,
    )
    fecha = fields.Date(string='Fecha', required=True, default=fields.Date.today)
    granja_id = fields.Many2one('avicola.granja', string='Granja', required=True)
    galpon_id = fields.Many2one(
        'avicola.galpon', string='Galpón', required=True,
        domain="[('granja_id', '=', granja_id)]"
    )
    cantidad = fields.Integer(string='Cantidad Mortalidad', required=True)
    observaciones = fields.Text(string='Observaciones')
    estado = fields.Selection(
        [('borrador', 'Borrador'), ('confirmado', 'Confirmado')],
        string='Estado', default='borrador', required=True
    )

    @api.depends('galpon_id')
    def _compute_lote_incubadora(self):
        for rec in self:
            if rec.galpon_id:
                dist = self.env['avicola.distribucion'].search([
                    ('galpon_id', '=', rec.galpon_id.id),
                    ('estado', '=', 'confirmado')
                ], order='fecha desc, id desc', limit=1)
                rec.lote_incubadora = dist.lote_incubadora if dist else False
            else:
                rec.lote_incubadora = False

    def action_confirmar(self):
        for rec in self:
            if rec.estado == 'confirmado':
                raise UserError('Este registro ya está confirmado.')
            if not rec.galpon_id:
                raise UserError('Debe seleccionar un galpón.')
            if rec.cantidad <= 0:
                raise UserError('La cantidad debe ser mayor a cero.')
            if rec.galpon_id.cantidad_actual < rec.cantidad:
                raise UserError(
                    f'No hay suficientes aves en el galpón para registrar esta mortalidad. '
                    f'Disponible: {rec.galpon_id.cantidad_actual}, solicitado: {rec.cantidad}'
                )
            rec.galpon_id.cantidad_actual -= rec.cantidad
            rec.estado = 'confirmado'

    def action_borrador(self):
        for rec in self:
            if rec.estado == 'confirmado':
                rec.galpon_id.cantidad_actual += rec.cantidad
            rec.estado = 'borrador'


class AvicolaSalida(models.Model):
    _name = 'avicola.salida'
    _description = 'Salida a Matadero'
    _order = 'fecha desc, id desc'

    fecha = fields.Date(string='Fecha', required=True, default=fields.Date.today)
    granja_id = fields.Many2one('avicola.granja', string='Granja', required=True)
    galpon_id = fields.Many2one(
        'avicola.galpon', string='Galpón',
        domain="[('granja_id', '=', granja_id)]"
    )
    cantidad = fields.Integer(string='Cantidad', required=True)
    peso_total = fields.Float(string='Peso Total (kg)', digits=(10, 2))
    estado = fields.Selection(
        [('borrador', 'Borrador'), ('confirmado', 'Confirmado')],
        string='Estado', default='borrador', required=True
    )

    def action_confirmar(self):
        for rec in self:
            if rec.estado == 'confirmado':
                raise UserError('Este registro ya está confirmado.')
            if rec.galpon_id:
                if rec.galpon_id.cantidad_actual < rec.cantidad:
                    raise UserError(
                        f'No hay suficientes aves en el galpón. '
                        f'Disponible: {rec.galpon_id.cantidad_actual}, '
                        f'Solicitado: {rec.cantidad}'
                    )
                rec.galpon_id.cantidad_actual -= rec.cantidad
            rec.estado = 'confirmado'

    def action_borrador(self):
        for rec in self:
            if rec.estado == 'confirmado' and rec.galpon_id:
                rec.galpon_id.cantidad_actual += rec.cantidad
            rec.estado = 'borrador'


class AvicolaVeterinario(models.Model):
    _name = 'avicola.veterinario'
    _description = 'Veterinario'
    _order = 'name'

    name = fields.Char(string='Nombre', required=True)
    user_id = fields.Many2one('res.users', string='Usuario', help='Usuario asociado al veterinario')
    granja_ids = fields.Many2many('avicola.granja', string='Granjas Asignadas')
    active = fields.Boolean(string='Activo', default=True)

    @api.onchange('user_id')
    def _onchange_user_id(self):
        for rec in self:
            if rec.user_id:
                rec.name = rec.user_id.name

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('user_id'):
                existing = self.search([('user_id', '=', vals['user_id'])], limit=1)
                if existing:
                    raise UserError('Este usuario ya está asignado a otro veterinario.')
                if not vals.get('name'):
                    user = self.env['res.users'].browse(vals['user_id'])
                    vals['name'] = user.name or user.login
        records = super().create(vals_list)
        try:
            vet_group = self.env.ref('gestion_avicola.group_veterinario', raise_if_not_found=False)
        except Exception:
            vet_group = None
        if vet_group:
            for rec in records:
                if rec.user_id and vet_group not in rec.user_id.all_group_ids:
                    rec.user_id.sudo().write({'group_ids': [(4, vet_group.id)]})
        return records

    def write(self, vals):
        res = super().write(vals)
        try:
            vet_group = self.env.ref('gestion_avicola.group_veterinario', raise_if_not_found=False)
        except Exception:
            vet_group = None
        if vet_group and 'user_id' in vals:
            for rec in self:
                if rec.user_id and vet_group not in rec.user_id.all_group_ids:
                    rec.user_id.sudo().write({'group_ids': [(4, vet_group.id)]})
        return res


class AvicolaPlanVacunacion(models.Model):
    _name = 'avicola.plan.vacunacion'
    _description = 'Planificación de Vacunación'
    _order = 'fecha_planificada desc, id desc'

    name = fields.Char(string='Referencia', default='Plan de Vacunación', required=True)
    veterinario_id = fields.Many2one(
        'avicola.veterinario', string='Veterinario', required=True,
        default=lambda self: self._default_veterinario()
    )
    granja_id = fields.Many2one('avicola.granja', string='Granja', required=True)
    fecha_planificada = fields.Date(string='Fecha Planificada', required=True, default=fields.Date.today)
    descripcion = fields.Text(string='Descripción')
    user_is_veterinario = fields.Boolean(string='Usuario es veterinario', compute='_compute_user_is_veterinario')
    state = fields.Selection(
        [('borrador', 'Borrador'), ('programado', 'Programado'), ('realizado', 'Realizado')],
        string='Estado', default='borrador', required=True
    )

    @api.model
    def _default_veterinario(self):
        if self.env.uid:
            vet = self.env['avicola.veterinario'].search([('user_id', '=', self.env.uid)], limit=1)
            return vet.id if vet else False
        return False

    @api.depends()
    def _compute_user_is_veterinario(self):
        current_user = self.env.uid
        is_vet = bool(self.env['avicola.veterinario'].search([('user_id', '=', current_user)], limit=1))
        for rec in self:
            rec.user_is_veterinario = is_vet

    @api.onchange('veterinario_id')
    def _onchange_veterinario_id(self):
        for rec in self:
            if rec.veterinario_id and rec.veterinario_id.granja_ids:
                allowed = rec.veterinario_id.granja_ids.ids
                if rec.granja_id and rec.granja_id.id not in allowed:
                    rec.granja_id = False
                return {'domain': {'granja_id': [('id', 'in', allowed)]}}
            else:
                return {'domain': {'granja_id': []}}

    def action_programar(self):
        for rec in self:
            rec.state = 'programado'

    def action_realizar(self):
        for rec in self:
            rec.state = 'realizado'

    def write(self, vals):
        if 'veterinario_id' in vals and not self.env.user.has_group('base.group_system'):
            vet = self.env['avicola.veterinario'].search([('user_id', '=', self.env.uid)], limit=1)
            if vet:
                for rec in self:
                    if rec.veterinario_id and vals.get('veterinario_id') and rec.veterinario_id.id != vals.get('veterinario_id'):
                        raise UserError('No tienes permiso para cambiar el Veterinario.')
        return super().write(vals)


class AvicolaDespacho(models.Model):
    _name = 'avicola.despacho'
    _description = 'Despacho de Aves Vivas'
    _order = 'fecha desc, id desc'

    name = fields.Char(string='Número de Ticket', required=True, copy=False, readonly=True, default=lambda self: self._generate_sequence())
    
    # Datos fijos
    company_name = fields.Char(string='Empresa', default='DESPACHO AVES VIVAS\nAgrolucha, C.A.', readonly=True)
    company_rif = fields.Char(string='RIF', default='J-00089080-3', readonly=True)
    company_direccion = fields.Text(string='Dirección', default='Av. Las Delicias, Edf. Banvenez, piso Mzz 2 of. Mzz2, Urb. El Bosque Maracay Aragua.', readonly=True)

    # Datos de operación
    fecha = fields.Datetime(string='Fecha', default=fields.Datetime.now, required=True)
    granja = fields.Many2one('avicola.granja', string='Granja', required=True)
    galpon_id = fields.Many2one('avicola.galpon', string='Galpón', domain="[('granja_id', '=', granja)]")
    cliente = fields.Char(string='Cliente', required=True)
    placa = fields.Char(string='Placa del Vehículo')
    chofer = fields.Char(string='Nombre del Chofer')
    cant_jaulas = fields.Integer(string='Cant. Jaulas')
    pollos_por_jaula = fields.Integer(string='Pollos/jaula')
    orden_compra = fields.Char(string='Orden de compra Nro')
    inicio_carga = fields.Datetime(string='Inicio de carga')
    final_carga = fields.Datetime(string='Final de carga')
    cuadrilla = fields.Char(string='Cuadrilla')
    cantidad_aves = fields.Integer(string='Cant. Aves', required=True)
    peso_neto = fields.Float(string='Peso Neto (kg)', digits=(12, 2))
    peso_promedio = fields.Float(string='Peso Promedio (kg)', compute='_compute_peso_promedio', store=True, digits=(10, 3))
    pollo_mojado = fields.Selection([('si', 'Sí'), ('no', 'No')], string='Pollo mojado', default='no')
    precinto_1 = fields.Char(string='Precinto 1')
    precinto_2 = fields.Char(string='Precinto 2')
    precinto = fields.Char(string='Precinto')
    supervisor = fields.Many2one('res.users', string='Supervisor', default=lambda self: self.env.user)
    estado = fields.Selection([
        ('borrador', 'Borrador'),
        ('confirmado', 'Confirmado'),
        ('cancelado', 'Cancelado')
    ], string='Estado', default='borrador', required=True)
    salida_id = fields.Many2one('avicola.salida', string='Salida relacionada', ondelete='set null', readonly=True)

    @api.model
    def _generate_sequence(self):
        count = self.search_count([]) + 1
        return f"DSP-{fields.Date.today().strftime('%Y%m')}-{count:04d}"

    @api.depends('peso_neto', 'cantidad_aves')
    def _compute_peso_promedio(self):
        for rec in self:
            if rec.cantidad_aves and rec.cantidad_aves > 0:
                rec.peso_promedio = float(rec.peso_neto or 0.0) / float(rec.cantidad_aves)
            else:
                rec.peso_promedio = 0.0

    def action_confirm_despacho(self):
        for rec in self:
            if rec.estado == 'confirmado':
                raise UserError('Este despacho ya está confirmado.')
            if rec.cantidad_aves <= 0:
                raise UserError('La cantidad de aves debe ser mayor a cero.')
            
            # Descontar del galpón si está seleccionado
            if rec.galpon_id:
                if rec.galpon_id.cantidad_actual < rec.cantidad_aves:
                    raise UserError(
                        f'No hay suficientes aves en el galpón {rec.galpon_id.name}. '
                        f'Disponibles: {rec.galpon_id.cantidad_actual}, '
                        f'Solicitadas: {rec.cantidad_aves}'
                    )
                rec.galpon_id.cantidad_actual -= rec.cantidad_aves

            # Crear o actualizar salida vinculada
            fecha_date = rec.fecha.date() if rec.fecha else fields.Date.today()
            if not rec.salida_id:
                salida = self.env['avicola.salida'].create({
                    'fecha': fecha_date,
                    'granja_id': rec.granja.id,
                    'galpon_id': rec.galpon_id.id if rec.galpon_id else False,
                    'cantidad': rec.cantidad_aves,
                    'peso_total': rec.peso_neto or 0.0,
                    'estado': 'confirmado',
                })
                rec.salida_id = salida.id
            else:
                rec.salida_id.write({
                    'fecha': fecha_date,
                    'granja_id': rec.granja.id,
                    'galpon_id': rec.galpon_id.id if rec.galpon_id else False,
                    'cantidad': rec.cantidad_aves,
                    'peso_total': rec.peso_neto or 0.0,
                    'estado': 'confirmado',
                })

            rec.estado = 'confirmado'

    def action_borrador(self):
        for rec in self:
            if rec.estado == 'confirmado':
                if rec.galpon_id:
                    rec.galpon_id.cantidad_actual += rec.cantidad_aves
                if rec.salida_id:
                    rec.salida_id.estado = 'borrador'
            rec.estado = 'borrador'

    def action_cancelar(self):
        for rec in self:
            if rec.estado == 'confirmado':
                if rec.galpon_id:
                    rec.galpon_id.cantidad_actual += rec.cantidad_aves
                if rec.salida_id:
                    rec.salida_id.unlink()
                    rec.salida_id = False
            rec.estado = 'cancelado'

    def action_print_ticket(self):
        self.ensure_one()
        return self.env.ref('gestion_avicola.action_report_ticket_despacho').report_action(self)


class AvicolaDashboard(models.Model):
    _name = 'avicola.dashboard'
    _description = 'Panel de Control Avícola'

    name = fields.Char(string="Dashboard", default="Panel de Control Avícola")
    selected_granja_id = fields.Many2one('avicola.granja', string='Filtrar por Granja')
    mortalidad_percent = fields.Float(
        string='Mortalidad (%)',
        compute='_compute_mortalidad_percent',
        digits=(10, 2)
    )

    total_granjas = fields.Integer(string='Total Granjas', compute='_compute_metrics')
    total_galpones = fields.Integer(string='Total Galpones Activos', compute='_compute_metrics')
    total_aves = fields.Integer(string='Población Actual de Aves', compute='_compute_metrics')
    total_veterinarios = fields.Integer(string='Veterinarios Activos', compute='_compute_metrics')
    total_ingresos_pollitos = fields.Integer(string='Pollitos Ingresados', compute='_compute_metrics')
    total_salidas_matadero = fields.Integer(string='Aves Sacrificadas / Despachadas', compute='_compute_metrics')
    peso_total_despachado = fields.Float(string='Total Kilos Despachados (kg)', compute='_compute_metrics', digits=(10, 2))

    def _get_visible_granjas(self):
        veterinarian = self.env['avicola.veterinario'].search([
            ('user_id', '=', self.env.uid),
        ], limit=1)
        if veterinarian and veterinarian.granja_ids:
            return veterinarian.granja_ids
        return self.env['avicola.granja'].search([])

    def _compute_metrics(self):
        Dist = self.env['avicola.distribucion']
        Salida = self.env['avicola.salida']
        Despacho = self.env['avicola.despacho']

        for rec in self:
            visible_granjas = rec._get_visible_granjas()
            rec.total_granjas = len(visible_granjas)

            galpones = self.env['avicola.galpon'].search([
                ('granja_id', 'in', visible_granjas.ids)
            ])
            rec.total_galpones = len(galpones)
            rec.total_aves = sum(galpones.mapped('cantidad_actual'))

            rec.total_ingresos_pollitos = sum(
                Dist.search([
                    ('estado', '=', 'confirmado'),
                    ('granja_id', 'in', visible_granjas.ids)
                ]).mapped('cantidad')
            )

            salidas_confirmadas = Salida.search([
                ('estado', '=', 'confirmado'),
                ('granja_id', 'in', visible_granjas.ids)
            ])
            despachos_confirmados = Despacho.search([
                ('estado', '=', 'confirmado'),
                ('granja', 'in', visible_granjas.ids)
            ])
            
            cant_salidas = sum(salidas_confirmadas.mapped('cantidad'))
            cant_despachos = sum(despachos_confirmados.mapped('cantidad_aves'))
            rec.total_salidas_matadero = cant_salidas or cant_despachos

            peso_salidas = sum(salidas_confirmadas.mapped('peso_total'))
            peso_despachos = sum(despachos_confirmados.mapped('peso_neto'))
            rec.peso_total_despachado = peso_salidas or peso_despachos

            rec.total_veterinarios = self.env['avicola.veterinario'].search_count([])

    @api.depends('selected_granja_id')
    def _compute_mortalidad_percent(self):
        for rec in self:
            Dist = self.env['avicola.distribucion']
            Mort = self.env['avicola.mortalidad']
            domain = [('estado', '=', 'confirmado')]
            if rec.selected_granja_id:
                domain.append(('granja_id', '=', rec.selected_granja_id.id))
            
            total_ingresos = sum(Dist.search(domain).mapped('cantidad'))
            total_mortalidad = sum(Mort.search(domain).mapped('cantidad'))

            if total_ingresos > 0:
                rec.mortalidad_percent = (float(total_mortalidad) * 100.0) / float(total_ingresos)
            else:
                rec.mortalidad_percent = 0.0

    def action_open_granjas(self):
        return {
            'name': 'Granjas',
            'type': 'ir.actions.act_window',
            'res_model': 'avicola.granja',
            'view_mode': 'list,form',
            'target': 'current',
        }

    def action_open_galpones(self):
        return {
            'name': 'Galpones',
            'type': 'ir.actions.act_window',
            'res_model': 'avicola.galpon',
            'view_mode': 'list,form,graph,pivot',
            'target': 'current',
        }

    def action_open_distribuciones(self):
        return {
            'name': 'Distribuciones',
            'type': 'ir.actions.act_window',
            'res_model': 'avicola.distribucion',
            'view_mode': 'list,form,graph',
            'target': 'current',
        }

    def action_open_mortalidad(self):
        domain = []
        if self.selected_granja_id:
            domain = [('granja_id', '=', self.selected_granja_id.id)]
        return {
            'name': 'Mortalidad de Aves',
            'type': 'ir.actions.act_window',
            'res_model': 'avicola.mortalidad',
            'view_mode': 'list,form,graph',
            'target': 'current',
            'domain': domain,
        }

    def action_open_salidas(self):
        return {
            'name': 'Despachos de Aves Vivas',
            'type': 'ir.actions.act_window',
            'res_model': 'avicola.despacho',
            'view_mode': 'list,form',
            'target': 'current',
        }

    def action_open_veterinarios(self):
        return {
            'name': 'Veterinarios',
            'type': 'ir.actions.act_window',
            'res_model': 'avicola.veterinario',
            'view_mode': 'list,form',
            'target': 'current',
        }

    def action_open_planificaciones(self):
        return {
            'name': 'Planificaciones de Vacunación',
            'type': 'ir.actions.act_window',
            'res_model': 'avicola.plan.vacunacion',
            'view_mode': 'list,form',
            'target': 'current',
        }


class ResUsers(models.Model):
    _inherit = 'res.users'

    def write(self, vals):
        res = super().write(vals)
        try:
            vet_group = self.env.ref('gestion_avicola.group_veterinario', raise_if_not_found=False)
        except Exception:
            vet_group = None
        if vet_group:
            for user in self:
                if vet_group in user.all_group_ids:
                    vet = self.env['avicola.veterinario'].search([('user_id', '=', user.id)], limit=1)
                    if not vet:
                        self.env['avicola.veterinario'].create({
                            'user_id': user.id,
                            'name': user.name or user.login,
                        })
        return res
