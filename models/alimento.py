# -*- coding: utf-8 -*-
import html
import logging
from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AvicolaAlimentoTipo(models.Model):
    _name = 'avicola.alimento.tipo'
    _description = 'Tipo y Fase de Alimento Balanceado'
    _order = 'fase, name'

    name = fields.Char(string='Nombre de la Fórmula', required=True)
    codigo = fields.Char(string='Código', required=True)
    fase = fields.Selection([
        ('pre_inicio', 'Pre-iniciador (0 - 7 días)'),
        ('inicio', 'Iniciador (8 - 21 días)'),
        ('engorde', 'Crecimiento / Engorde (22 - 35 días)'),
        ('finalizador', 'Finalizador / Retiro (36+ días)'),
    ], string='Fase de Crianza', default='inicio', required=True)
    proteina_pct = fields.Float(string='% Proteína Cruda (PC)', digits=(5, 2), default=20.0)
    energia_kcal = fields.Float(string='Energía Metabolizable (kcal/kg)', digits=(6, 2), default=3100.0)
    costo_por_kg = fields.Float(string='Costo Referencial ($/kg)', digits=(10, 2), default=0.45)
    color = fields.Char(string='Color Identificador', default='#144D34')
    descripcion = fields.Text(string='Descripción y Especificaciones')
    active = fields.Boolean(string='Activo', default=True)


class AvicolaAlimentoDespacho(models.Model):
    _name = 'avicola.alimento.despacho'
    _description = 'Despacho de Alimento a Granja'
    _order = 'fecha desc, id desc'

    name = fields.Char(
        string='Nro de Despacho',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: self._generate_sequence()
    )
    fecha = fields.Date(string='Fecha de Despacho', default=fields.Date.today, required=True)
    granja_id = fields.Many2one('avicola.granja', string='Granja Destino', required=True)
    galpon_id = fields.Many2one(
        'avicola.galpon', string='Galpón / Silo Específico',
        domain="[('granja_id', '=', granja_id)]",
        help='Opcional si se despacha al silo general de la granja'
    )
    tipo_alimento_id = fields.Many2one('avicola.alimento.tipo', string='Tipo de Alimento', required=True)
    lote_alimento = fields.Char(string='Lote de Planta')
    cantidad_kg = fields.Float(string='Cantidad Despachada (kg)', required=True, digits=(12, 2))
    cantidad_ton = fields.Float(string='Cantidad (Toneladas)', compute='_compute_toneladas', store=True, digits=(10, 3))
    presentacion = fields.Selection([
        ('granel', 'A Granel (Silo / Tolva)'),
        ('sacos', 'En Sacos (40 kg)'),
    ], string='Presentación', default='granel', required=True)
    cantidad_sacos = fields.Integer(string='Nro de Sacos', compute='_compute_sacos', store=True, readonly=False)
    chofer = fields.Char(string='Chofer')
    placa = fields.Char(string='Placa de Camión')
    planta_origen = fields.Char(string='Planta / Proveedor', default='Planta Principal de Alimentos Balanceados')
    costo_total = fields.Float(string='Costo Total Estimado ($)', compute='_compute_costo_total', store=True, digits=(12, 2))
    observaciones = fields.Text(string='Observaciones')
    estado = fields.Selection([
        ('borrador', 'Borrador'),
        ('confirmado', 'Confirmado (En Silo)'),
        ('cancelado', 'Cancelado')
    ], string='Estado', default='borrador', required=True)

    @api.model
    def _generate_sequence(self):
        count = self.search_count([]) + 1
        return f"DSP-ALM-{fields.Date.today().strftime('%Y%m')}-{count:04d}"

    @api.depends('cantidad_kg')
    def _compute_toneladas(self):
        for rec in self:
            rec.cantidad_ton = (rec.cantidad_kg or 0.0) / 1000.0

    @api.depends('cantidad_kg', 'presentacion')
    def _compute_sacos(self):
        for rec in self:
            if rec.presentacion == 'sacos' and rec.cantidad_kg:
                rec.cantidad_sacos = int(rec.cantidad_kg / 40.0)
            elif rec.presentacion == 'granel':
                rec.cantidad_sacos = 0

    @api.depends('cantidad_kg', 'tipo_alimento_id', 'tipo_alimento_id.costo_por_kg')
    def _compute_costo_total(self):
        for rec in self:
            costo_unit = rec.tipo_alimento_id.costo_por_kg if rec.tipo_alimento_id else 0.0
            rec.costo_total = (rec.cantidad_kg or 0.0) * costo_unit

    def action_confirmar(self):
        for rec in self:
            if rec.estado == 'confirmado':
                raise UserError('Este despacho de alimento ya fue confirmado.')
            if rec.cantidad_kg <= 0:
                raise UserError('La cantidad despachada en kilogramos debe ser mayor a cero.')
            rec.estado = 'confirmado'

    def action_borrador(self):
        for rec in self:
            rec.estado = 'borrador'

    def action_cancelar(self):
        for rec in self:
            rec.estado = 'cancelado'


class AvicolaAlimentoConsumo(models.Model):
    _name = 'avicola.alimento.consumo'
    _description = 'Registro de Consumo Diario de Alimento'
    _order = 'fecha desc, id desc'

    name = fields.Char(
        string='Referencia de Consumo',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: self._generate_sequence()
    )
    fecha = fields.Date(string='Fecha', default=fields.Date.today, required=True)
    granja_id = fields.Many2one('avicola.granja', string='Granja', required=True)
    galpon_id = fields.Many2one(
        'avicola.galpon', string='Galpón', required=True,
        domain="[('granja_id', '=', granja_id)]"
    )
    tipo_alimento_id = fields.Many2one('avicola.alimento.tipo', string='Tipo de Alimento Consumido', required=True)
    cantidad_kg = fields.Float(string='Alimento Consumido (kg)', required=True, digits=(10, 2))
    cantidad_aves = fields.Integer(string='Población de Aves Activa', compute='_compute_aves', store=True, readonly=False)
    consumo_ave_dia_gr = fields.Float(
        string='Consumo Promedio (g/ave/día)',
        compute='_compute_consumo_ave',
        store=True,
        digits=(8, 2)
    )
    observaciones = fields.Text(string='Observaciones / Registro de Silo')
    estado = fields.Selection([
        ('borrador', 'Borrador'),
        ('confirmado', 'Confirmado')
    ], string='Estado', default='borrador', required=True)

    @api.model
    def _generate_sequence(self):
        count = self.search_count([]) + 1
        return f"CNS-ALM-{fields.Date.today().strftime('%Y%m')}-{count:04d}"

    @api.depends('galpon_id')
    def _compute_aves(self):
        for rec in self:
            if rec.galpon_id:
                rec.cantidad_aves = rec.galpon_id.cantidad_actual
            else:
                rec.cantidad_aves = 0

    @api.depends('cantidad_kg', 'cantidad_aves')
    def _compute_consumo_ave(self):
        for rec in self:
            if rec.cantidad_aves and rec.cantidad_aves > 0 and rec.cantidad_kg:
                rec.consumo_ave_dia_gr = (rec.cantidad_kg * 1000.0) / rec.cantidad_aves
            else:
                rec.consumo_ave_dia_gr = 0.0

    def action_confirmar(self):
        for rec in self:
            if rec.estado == 'confirmado':
                raise UserError('Este registro de consumo ya está confirmado.')
            if rec.cantidad_kg <= 0:
                raise UserError('La cantidad consumida debe ser mayor a cero.')
            
            # Validar que la granja tenga suficiente stock de alimento
            stock_disp = rec.granja_id.stock_alimento_kg
            if stock_disp < rec.cantidad_kg:
                raise UserError(
                    f'No hay suficiente alimento disponible en {rec.granja_id.name}.\n'
                    f'Stock disponible: {stock_disp:,.2f} kg, Solicitado para consumo: {rec.cantidad_kg:,.2f} kg.\n'
                    f'Por favor registre primero un Despacho de Alimento para reabastecer el silo.'
                )
            rec.estado = 'confirmado'

    def action_borrador(self):
        for rec in self:
            rec.estado = 'borrador'


class AvicolaGranjaAlimento(models.Model):
    _inherit = 'avicola.granja'

    despacho_alimento_ids = fields.One2many(
        'avicola.alimento.despacho', 'granja_id', string='Despachos de Alimento'
    )
    consumo_alimento_ids = fields.One2many(
        'avicola.alimento.consumo', 'granja_id', string='Consumos de Alimento'
    )
    total_alimento_recibido_kg = fields.Float(
        string='Alimento Recibido (kg)',
        compute='_compute_alimento_totales',
        store=True,
        digits=(12, 2)
    )
    total_alimento_consumido_kg = fields.Float(
        string='Alimento Consumido (kg)',
        compute='_compute_alimento_totales',
        store=True,
        digits=(12, 2)
    )
    stock_alimento_kg = fields.Float(
        string='Stock Disponible en Silos (kg)',
        compute='_compute_alimento_totales',
        store=True,
        digits=(12, 2)
    )
    stock_alimento_ton = fields.Float(
        string='Stock Disponible (Ton)',
        compute='_compute_alimento_totales',
        store=True,
        digits=(10, 2)
    )

    @api.depends('despacho_alimento_ids.cantidad_kg', 'despacho_alimento_ids.estado',
                 'consumo_alimento_ids.cantidad_kg', 'consumo_alimento_ids.estado')
    def _compute_alimento_totales(self):
        for rec in self:
            despachos_confirmados = rec.despacho_alimento_ids.filtered(lambda d: d.estado == 'confirmado')
            consumos_confirmados = rec.consumo_alimento_ids.filtered(lambda c: c.estado == 'confirmado')

            rec.total_alimento_recibido_kg = sum(despachos_confirmados.mapped('cantidad_kg'))
            rec.total_alimento_consumido_kg = sum(consumos_confirmados.mapped('cantidad_kg'))
            rec.stock_alimento_kg = rec.total_alimento_recibido_kg - rec.total_alimento_consumido_kg
            rec.stock_alimento_ton = rec.stock_alimento_kg / 1000.0


class AvicolaGalponAlimento(models.Model):
    _inherit = 'avicola.galpon'

    consumo_alimento_ids = fields.One2many(
        'avicola.alimento.consumo', 'galpon_id', string='Consumos de Alimento'
    )
    total_alimento_consumido_kg = fields.Float(
        string='Consumo Total Alimento (kg)',
        compute='_compute_alimento_galpon',
        store=True,
        digits=(12, 2)
    )

    @api.depends('consumo_alimento_ids.cantidad_kg', 'consumo_alimento_ids.estado')
    def _compute_alimento_galpon(self):
        for rec in self:
            confirmados = rec.consumo_alimento_ids.filtered(lambda c: c.estado == 'confirmado')
            rec.total_alimento_consumido_kg = sum(confirmados.mapped('cantidad_kg'))


class AvicolaAlimentoDashboard(models.Model):
    _name = 'avicola.alimento.dashboard'
    _description = 'Panel de Gestión y Analítica de Alimento'

    name = fields.Char(string="Dashboard Alimento", default="Control de Alimento y Nutrición")
    selected_granja_id = fields.Many2one('avicola.granja', string='Filtrar por Granja')

    stock_total_kg = fields.Float(string='Stock Total (kg)', compute='_compute_metrics', digits=(12, 2))
    stock_total_ton = fields.Float(string='Stock Total (Ton)', compute='_compute_metrics', digits=(10, 2))
    consumo_total_kg = fields.Float(string='Consumo Total (kg)', compute='_compute_metrics', digits=(12, 2))
    despacho_total_kg = fields.Float(string='Despacho Total (kg)', compute='_compute_metrics', digits=(12, 2))
    consumo_promedio_dia_gr = fields.Float(string='Consumo Prom. por Ave (g/día)', compute='_compute_metrics', digits=(8, 2))

    dashboard_html = fields.Html(
        string='Dashboard HTML',
        compute='_compute_dashboard_html',
        sanitize=False
    )

    def _compute_metrics(self):
        Despacho = self.env['avicola.alimento.despacho']
        Consumo = self.env['avicola.alimento.consumo']

        for rec in self:
            domain = []
            if rec.selected_granja_id:
                domain = [('granja_id', '=', rec.selected_granja_id.id)]

            despachos = Despacho.search([('estado', '=', 'confirmado')] + domain)
            consumos = Consumo.search([('estado', '=', 'confirmado')] + domain)

            rec.despacho_total_kg = sum(despachos.mapped('cantidad_kg'))
            rec.consumo_total_kg = sum(consumos.mapped('cantidad_kg'))
            rec.stock_total_kg = rec.despacho_total_kg - rec.consumo_total_kg
            rec.stock_total_ton = rec.stock_total_kg / 1000.0

            promedios = consumos.mapped('consumo_ave_dia_gr')
            rec.consumo_promedio_dia_gr = (sum(promedios) / len(promedios)) if promedios else 0.0

    def _compute_dashboard_html(self):
        for rec in self:
            rec._compute_metrics()

            domain = [('granja_id', '=', rec.selected_granja_id.id)] if rec.selected_granja_id else []
            despachos = self.env['avicola.alimento.despacho'].search([('estado', '=', 'confirmado')] + domain, limit=5, order='fecha desc, id desc')
            consumos = self.env['avicola.alimento.consumo'].search([('estado', '=', 'confirmado')] + domain, limit=5, order='fecha desc, id desc')

            stock_kg = rec.stock_total_kg
            stock_ton = rec.stock_total_ton
            despacho_kg = rec.despacho_total_kg
            consumo_kg = rec.consumo_total_kg
            consumo_ave_gr = rec.consumo_promedio_dia_gr

            # Desglose de consumo por tipo de alimento real
            tipos = self.env['avicola.alimento.tipo'].search([])
            breakdown_html = ""
            colors = ["#144D34", "#34D399", "#3b82f6", "#f59e0b", "#8b5cf6"]
            if tipos and consumo_kg > 0:
                for i, t in enumerate(tipos):
                    c = colors[i % len(colors)]
                    tipo_consumos = self.env['avicola.alimento.consumo'].search([
                        ('tipo_alimento_id', '=', t.id),
                        ('estado', '=', 'confirmado')
                    ] + domain)
                    kg = sum(tipo_consumos.mapped('cantidad_kg'))
                    pct = ((kg / consumo_kg) * 100.0) if consumo_kg > 0 else 0.0
                    if kg > 0:
                        breakdown_html += f"""
                        <div style="margin-bottom: 14px;">
                            <div style="display: flex; justify-content: space-between; font-size: 13px; font-weight: 600; color: #0f172a; margin-bottom: 5px;">
                                <span>{html.escape(t.name)}</span>
                                <span>{kg:,.0f} kg ({pct:.1f}%)</span>
                            </div>
                            <div style="width: 100%; height: 8px; background: #e2e8f0; border-radius: 999px; overflow: hidden;">
                                <div style="width: {min(100, pct):.1f}%; height: 100%; background: {c}; border-radius: 999px;"></div>
                            </div>
                        </div>
                        """
            
            if not breakdown_html:
                breakdown_html = """
                <div style="display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 25px 0; text-align: center; color: #64748b;">
                    <i class="fa fa-pie-chart" style="font-size: 28px; color: #cbd5e1; margin-bottom: 8px;"></i>
                    <div style="font-size: 13px; font-weight: 600; color: #334155;">Sin consumos registrados</div>
                    <div style="font-size: 11px; margin-bottom: 10px;">Registra el consumo diario de los galpones</div>
                    <a href="/web#action=gestion_avicola.action_avicola_alimento_consumo" class="btn btn-sm" style="background: #144D34; color: white; border-radius: 999px; padding: 5px 14px; font-size: 11px; text-decoration: none;">+ Registrar Consumo</a>
                </div>
                """

            # Recent Food Dispatches Reales
            recent_desp_html = ""
            if despachos:
                for d in despachos:
                    dt = d.fecha.strftime('%d/%m/%Y') if d.fecha else 'Hoy'
                    recent_desp_html += f"""
                    <a href="/web#id={d.id}&model=avicola.alimento.despacho&view_type=form" style="display: flex; align-items: center; justify-content: space-between; padding: 9px 0; border-bottom: 1px solid #f1f5f9; text-decoration: none; color: inherit;">
                        <div style="display: flex; align-items: center; gap: 10px;">
                            <div style="width: 32px; height: 32px; border-radius: 8px; background: #144D3415; color: #144D34; display: flex; align-items: center; justify-content: center; font-size: 13px;">
                                <i class="fa fa-truck"></i>
                            </div>
                            <div>
                                <div style="font-size: 13px; font-weight: 600; color: #0f172a;">{d.name} • {html.escape(d.granja_id.name)}</div>
                                <div style="font-size: 11px; color: #64748b;">{dt} • {html.escape(d.tipo_alimento_id.name)} • {d.presentacion.title()}</div>
                            </div>
                        </div>
                        <span style="font-size: 12px; font-weight: 700; color: #144D34;">+{d.cantidad_kg:,.0f} kg</span>
                    </a>
                    """
            else:
                recent_desp_html = """
                <div style="display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 25px 0; text-align: center; color: #64748b;">
                    <i class="fa fa-truck" style="font-size: 28px; color: #cbd5e1; margin-bottom: 8px;"></i>
                    <div style="font-size: 13px; font-weight: 600; color: #334155;">Sin despachos de alimento registrados</div>
                    <div style="font-size: 11px; margin-bottom: 10px;">Despacha alimento desde la planta o proveedor a los silos</div>
                    <a href="/web#action=gestion_avicola.action_avicola_alimento_despacho" class="btn btn-sm" style="background: #144D34; color: white; border-radius: 999px; padding: 5px 14px; font-size: 11px; text-decoration: none;">+ Despachar Alimento</a>
                </div>
                """

            rec.dashboard_html = f"""
            <style>
                .avicola-dash-wrapper {{
                    background: #f8fafc;
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    padding: 20px;
                    border-radius: 20px;
                    color: #0f172a;
                    box-sizing: border-box;
                }}
                .avicola-kpi-grid {{
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
                    gap: 16px;
                    margin-bottom: 24px;
                }}
                .avicola-grid-12 {{
                    display: grid;
                    grid-template-columns: repeat(12, 1fr);
                    gap: 16px;
                    margin-bottom: 24px;
                }}
                .avicola-col-span-6 {{ grid-column: span 6; }}

                @media (max-width: 991px) {{
                    .avicola-dash-wrapper {{
                        padding: 12px 6px !important;
                    }}
                    .avicola-header-block {{
                        flex-direction: column !important;
                        align-items: stretch !important;
                        gap: 12px !important;
                    }}
                    .avicola-btn-group {{
                        display: flex !important;
                        flex-direction: column !important;
                        width: 100% !important;
                        gap: 8px !important;
                    }}
                    .avicola-btn-group a {{
                        width: 100% !important;
                        justify-content: center !important;
                        text-align: center !important;
                        box-sizing: border-box !important;
                    }}
                    .avicola-kpi-grid {{
                        grid-template-columns: 1fr !important;
                        gap: 12px !important;
                        margin-bottom: 16px !important;
                    }}
                    .avicola-grid-12 {{
                        display: flex !important;
                        flex-direction: column !important;
                        gap: 14px !important;
                        margin-bottom: 16px !important;
                    }}
                    .avicola-col-span-6 {{
                        grid-column: auto !important;
                        width: 100% !important;
                        box-sizing: border-box !important;
                    }}
                    .avicola-bottom-card {{
                        flex-direction: column !important;
                        align-items: stretch !important;
                    }}
                    .avicola-bottom-actions {{
                        flex-direction: column !important;
                        width: 100% !important;
                    }}
                    .avicola-bottom-actions a {{
                        width: 100% !important;
                        justify-content: center !important;
                        text-align: center !important;
                    }}
                }}
            </style>
            <div class="avicola-dash-wrapper">
                
                <!-- TOP HEADER -->
                <div class="avicola-header-block" style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; flex-wrap: wrap; gap: 12px;">
                    <div>
                        <h1 style="font-size: 28px; font-weight: 800; color: #0f172a; margin: 0 0 4px 0; letter-spacing: -0.5px;">Gestión y Control de Alimento</h1>
                        <p style="font-size: 13px; color: #64748b; margin: 0;">Supervisión de despachos a silos, stock disponible y consumo diario de aves.</p>
                    </div>
                    <div class="avicola-btn-group" style="display: flex; align-items: center; gap: 10px; flex-wrap: wrap;">
                        <a href="/web#action=gestion_avicola.action_avicola_alimento_despacho" class="btn btn-sm" style="background: #144D34; color: #ffffff; border-radius: 999px; padding: 8px 18px; font-weight: 600; font-size: 13px; text-decoration: none; display: inline-flex; align-items: center; gap: 6px; box-shadow: 0 4px 10px rgba(20,77,52,0.2);">
                            <i class="fa fa-plus"></i> Despachar Alimento
                        </a>
                        <a href="/web#action=gestion_avicola.action_avicola_alimento_consumo" class="btn btn-sm" style="background: #ffffff; color: #0f172a; border: 1.5px solid #cbd5e1; border-radius: 999px; padding: 8px 18px; font-weight: 600; font-size: 13px; text-decoration: none; display: inline-flex; align-items: center; gap: 6px;">
                            <i class="fa fa-cutlery"></i> Registrar Consumo
                        </a>
                        <a href="/web#action=gestion_avicola.action_avicola_alimento_graficas" class="btn btn-sm" style="background: #ffffff; color: #144D34; border: 1.5px solid #a7f3d0; border-radius: 999px; padding: 8px 16px; font-weight: 600; font-size: 13px; text-decoration: none; display: inline-flex; align-items: center; gap: 6px;">
                            <i class="fa fa-bar-chart"></i> Analítica Dinámica
                        </a>
                    </div>
                </div>

                <!-- 4 TOP KPI CARDS -->
                <div class="avicola-kpi-grid">
                    
                    <!-- Card 1: Stock Total Alimento (Dark Forest Green) -->
                    <div style="background-color: #144D34; border-radius: 18px; padding: 22px; color: #ffffff; display: flex; flex-direction: column; justify-content: space-between; min-height: 140px; box-shadow: 0 6px 16px rgba(20,77,52,0.18);">
                        <div style="display: flex; justify-content: space-between; align-items: center;">
                            <span style="font-size: 13px; font-weight: 600; color: #a7f3d0;">Stock Actual en Silos</span>
                            <a href="/web#action=gestion_avicola.action_avicola_granja" title="Ver Granjas y Silos" style="text-decoration: none; width: 32px; height: 32px; border-radius: 50%; border: 1.5px solid rgba(255,255,255,0.4); background: rgba(255,255,255,0.15); display: flex; align-items: center; justify-content: center; font-size: 14px; color: #ffffff; cursor: pointer;">↗</a>
                        </div>
                        <div style="font-size: 34px; font-weight: 800; line-height: 1; margin: 14px 0; color: #ffffff;">{stock_kg:,.0f} <span style="font-size: 16px; font-weight: 500;">kg</span></div>
                        <div>
                            <span style="background: rgba(255,255,255,0.18); color: #ffffff; padding: 4px 10px; border-radius: 999px; font-size: 11px; font-weight: 600;">
                                {stock_ton:.2f} Toneladas Disponibles
                            </span>
                        </div>
                    </div>

                    <!-- Card 2: Alimento Despachado -->
                    <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 18px; padding: 22px; color: #0f172a; display: flex; flex-direction: column; justify-content: space-between; min-height: 140px; box-shadow: 0 2px 6px rgba(0,0,0,0.02);">
                        <div style="display: flex; justify-content: space-between; align-items: center;">
                            <span style="font-size: 13px; font-weight: 600; color: #64748b;">Alimento Despachado</span>
                            <a href="/web#action=gestion_avicola.action_avicola_alimento_despacho" title="Ver Despachos" style="text-decoration: none; width: 32px; height: 32px; border-radius: 50%; border: 1.5px solid #e2e8f0; background: #f8fafc; display: flex; align-items: center; justify-content: center; font-size: 14px; color: #334155; cursor: pointer;">↗</a>
                        </div>
                        <div style="font-size: 34px; font-weight: 800; line-height: 1; margin: 14px 0; color: #0f172a;">{despacho_kg:,.0f} <span style="font-size: 16px; font-weight: 500; color: #64748b;">kg</span></div>
                        <div>
                            <span style="background: #f1f5f9; color: #475569; padding: 4px 10px; border-radius: 999px; font-size: 11px; font-weight: 600;">
                                Envíos a Silos Realizados
                            </span>
                        </div>
                    </div>

                    <!-- Card 3: Consumo Acumulado -->
                    <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 18px; padding: 22px; color: #0f172a; display: flex; flex-direction: column; justify-content: space-between; min-height: 140px; box-shadow: 0 2px 6px rgba(0,0,0,0.02);">
                        <div style="display: flex; justify-content: space-between; align-items: center;">
                            <span style="font-size: 13px; font-weight: 600; color: #64748b;">Consumo Acumulado</span>
                            <a href="/web#action=gestion_avicola.action_avicola_alimento_consumo" title="Ver Consumos" style="text-decoration: none; width: 32px; height: 32px; border-radius: 50%; border: 1.5px solid #e2e8f0; background: #f8fafc; display: flex; align-items: center; justify-content: center; font-size: 14px; color: #334155; cursor: pointer;">↗</a>
                        </div>
                        <div style="font-size: 34px; font-weight: 800; line-height: 1; margin: 14px 0; color: #0f172a;">{consumo_kg:,.0f} <span style="font-size: 16px; font-weight: 500; color: #64748b;">kg</span></div>
                        <div>
                            <span style="background: #f1f5f9; color: #475569; padding: 4px 10px; border-radius: 999px; font-size: 11px; font-weight: 600;">
                                Consumido por Lotes en Crianza
                            </span>
                        </div>
                    </div>

                    <!-- Card 4: Consumo Ave/Día -->
                    <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 18px; padding: 22px; color: #0f172a; display: flex; flex-direction: column; justify-content: space-between; min-height: 140px; box-shadow: 0 2px 6px rgba(0,0,0,0.02);">
                        <div style="display: flex; justify-content: space-between; align-items: center;">
                            <span style="font-size: 13px; font-weight: 600; color: #64748b;">Consumo Promedio</span>
                            <a href="/web#action=gestion_avicola.action_avicola_alimento_graficas" title="Ver Analítica Dinámica" style="text-decoration: none; width: 32px; height: 32px; border-radius: 50%; border: 1.5px solid #e2e8f0; background: #f8fafc; display: flex; align-items: center; justify-content: center; font-size: 14px; color: #334155; cursor: pointer;">↗</a>
                        </div>
                        <div style="font-size: 34px; font-weight: 800; line-height: 1; margin: 14px 0; color: #0f172a;">{consumo_ave_gr:.1f} <span style="font-size: 16px; font-weight: 500; color: #64748b;">g</span></div>
                        <div>
                            <span style="background: #ecfdf5; color: #059669; padding: 4px 10px; border-radius: 999px; font-size: 11px; font-weight: 600;">
                                Gramos / Ave / Día
                            </span>
                        </div>
                    </div>

                </div>

                <!-- MIDDLE SECTION -->
                <div class="avicola-grid-12">
                    
                    <!-- Middle Left: Consumo por Tipo de Alimento (Fases) -->
                    <div class="avicola-col-span-6" style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 18px; padding: 22px; box-shadow: 0 2px 6px rgba(0,0,0,0.02);">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 18px;">
                            <div>
                                <h3 style="font-size: 15px; font-weight: 700; color: #0f172a; margin: 0;">Consumo por Fase / Tipo de Alimento</h3>
                                <div style="font-size: 12px; color: #64748b;">Distribución nutricional de la parvada</div>
                            </div>
                            <a href="/web#action=gestion_avicola.action_avicola_alimento_consumo" style="font-size: 12px; font-weight: 600; color: #144D34; text-decoration: none;">Ver Detalle →</a>
                        </div>
                        <div>
                            {breakdown_html}
                        </div>
                    </div>

                    <!-- Middle Right: Despachos Recientes a Silos -->
                    <div class="avicola-col-span-6" style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 18px; padding: 22px; box-shadow: 0 2px 6px rgba(0,0,0,0.02);">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                            <div>
                                <h3 style="font-size: 15px; font-weight: 700; color: #0f172a; margin: 0;">Últimos Despachos a Silos</h3>
                                <div style="font-size: 12px; color: #64748b;">Abastecimiento de alimento por granja</div>
                            </div>
                            <a href="/web#action=gestion_avicola.action_avicola_alimento_despacho" style="font-size: 12px; font-weight: 600; color: #144D34; text-decoration: none;">Ver Todos →</a>
                        </div>
                        <div>
                            {recent_desp_html}
                        </div>
                    </div>

                </div>

                <!-- BOTTOM ACCESS CARDS -->
                <div class="avicola-bottom-card" style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 18px; padding: 18px 22px; box-shadow: 0 2px 6px rgba(0,0,0,0.02); display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 14px;">
                    <div style="display: flex; align-items: center; gap: 12px;">
                        <div style="width: 40px; height: 40px; border-radius: 10px; background: #144D3415; color: #144D34; display: flex; align-items: center; justify-content: center; font-size: 18px;">
                            <i class="fa fa-bar-chart"></i>
                        </div>
                        <div>
                            <div style="font-size: 14px; font-weight: 700; color: #0f172a;">Analítica Dinámica e Informes</div>
                            <div style="font-size: 12px; color: #64748b;">Explora gráficas interactivas de evolución de consumo, pivotes por lote y stock de silos.</div>
                        </div>
                    </div>
                    <div class="avicola-bottom-actions" style="display: flex; gap: 8px; flex-wrap: wrap;">
                        <a href="/web#action=gestion_avicola.action_avicola_alimento_graficas" class="btn btn-sm" style="background: #f1f5f9; color: #144D34; border-radius: 10px; font-weight: 600; font-size: 12px; padding: 8px 14px; text-decoration: none;">
                            <i class="fa fa-line-chart me-1"></i> Gráfica de Consumos
                        </a>
                        <a href="/web#action=gestion_avicola.action_avicola_alimento_consumo" class="btn btn-sm" style="background: #f1f5f9; color: #144D34; border-radius: 10px; font-weight: 600; font-size: 12px; padding: 8px 14px; text-decoration: none;">
                            <i class="fa fa-table me-1"></i> Tabla Pivot
                        </a>
                        <a href="/web#action=gestion_avicola.action_avicola_alimento_despacho" class="btn btn-sm" style="background: #f1f5f9; color: #144D34; border-radius: 10px; font-weight: 600; font-size: 12px; padding: 8px 14px; text-decoration: none;">
                            <i class="fa fa-truck me-1"></i> Historial Despachos
                        </a>
                    </div>
                </div>

            </div>
            """

    def action_load_demo_alimento(self):
        self.ensure_one()
        granja_pinos = self.env['avicola.granja'].search([('name', '=', 'Granja Los Pinos')], limit=1)
        if not granja_pinos:
            granja_pinos = self.env['avicola.granja'].search([], limit=1)
        if not granja_pinos:
            # Primero poblar granjas base si no existen
            self.env['avicola.dashboard'].search([], limit=1).action_load_demo_data()
            granja_pinos = self.env['avicola.granja'].search([('name', '=', 'Granja Los Pinos')], limit=1)

        # Crear tipos de alimento si no existen
        t_pre = self.env['avicola.alimento.tipo'].search([('codigo', '=', 'ALM-PRE')], limit=1)
        if not t_pre:
            t_pre = self.env['avicola.alimento.tipo'].create({
                'name': 'Pre-iniciador Micro-Pellet',
                'codigo': 'ALM-PRE',
                'fase': 'pre_inicio',
                'proteina_pct': 22.5,
                'energia_kcal': 3050.0,
                'costo_por_kg': 0.52,
            })
        t_ini = self.env['avicola.alimento.tipo'].search([('codigo', '=', 'ALM-INI')], limit=1)
        if not t_ini:
            t_ini = self.env['avicola.alimento.tipo'].create({
                'name': 'Iniciador Pollito BB',
                'codigo': 'ALM-INI',
                'fase': 'inicio',
                'proteina_pct': 21.0,
                'energia_kcal': 3120.0,
                'costo_por_kg': 0.48,
            })
        t_eng = self.env['avicola.alimento.tipo'].search([('codigo', '=', 'ALM-ENG')], limit=1)
        if not t_eng:
            t_eng = self.env['avicola.alimento.tipo'].create({
                'name': 'Crecimiento / Engorde Plus',
                'codigo': 'ALM-ENG',
                'fase': 'engorde',
                'proteina_pct': 19.5,
                'energia_kcal': 3200.0,
                'costo_por_kg': 0.44,
            })
        t_fin = self.env['avicola.alimento.tipo'].search([('codigo', '=', 'ALM-FIN')], limit=1)
        if not t_fin:
            t_fin = self.env['avicola.alimento.tipo'].create({
                'name': 'Finalizador / Acabado',
                'codigo': 'ALM-FIN',
                'fase': 'finalizador',
                'proteina_pct': 18.0,
                'energia_kcal': 3250.0,
                'costo_por_kg': 0.42,
            })

        # Despachos de alimento demo
        if self.env['avicola.alimento.despacho'].search_count([]) == 0:
            d1 = self.env['avicola.alimento.despacho'].create({
                'fecha': fields.Date.today(),
                'granja_id': granja_pinos.id,
                'tipo_alimento_id': t_ini.id,
                'cantidad_kg': 15000.0,
                'presentacion': 'granel',
                'chofer': 'Manuel Barreto',
                'placa': 'A45BC89',
            })
            d1.action_confirmar()

            d2 = self.env['avicola.alimento.despacho'].create({
                'fecha': fields.Date.today(),
                'granja_id': granja_pinos.id,
                'tipo_alimento_id': t_eng.id,
                'cantidad_kg': 12000.0,
                'presentacion': 'granel',
                'chofer': 'Manuel Barreto',
                'placa': 'A45BC89',
            })
            d2.action_confirmar()

        # Consumo diario demo
        if self.env['avicola.alimento.consumo'].search_count([]) == 0 and granja_pinos.galpon_ids:
            g1 = granja_pinos.galpon_ids[0]
            c1 = self.env['avicola.alimento.consumo'].create({
                'fecha': fields.Date.today(),
                'granja_id': granja_pinos.id,
                'galpon_id': g1.id,
                'tipo_alimento_id': t_ini.id,
                'cantidad_kg': 1250.0,
                'cantidad_aves': g1.cantidad_actual or 12000,
            })
            c1.action_confirmar()

            if len(granja_pinos.galpon_ids) > 1:
                g2 = granja_pinos.galpon_ids[1]
                c2 = self.env['avicola.alimento.consumo'].create({
                    'fecha': fields.Date.today(),
                    'granja_id': granja_pinos.id,
                    'galpon_id': g2.id,
                    'tipo_alimento_id': t_eng.id,
                    'cantidad_kg': 980.0,
                    'cantidad_aves': g2.cantidad_actual or 10000,
                })
                c2.action_confirmar()

        self._compute_metrics()
        self._compute_dashboard_html()
        return True

    def action_new_despacho_alimento(self):
        return {
            'name': 'Nuevo Despacho de Alimento a Granja',
            'type': 'ir.actions.act_window',
            'res_model': 'avicola.alimento.despacho',
            'view_mode': 'form',
            'target': 'current',
            'context': {'default_granja_id': self.selected_granja_id.id if self.selected_granja_id else False},
        }

    def action_new_consumo_alimento(self):
        return {
            'name': 'Registrar Consumo Diario de Alimento',
            'type': 'ir.actions.act_window',
            'res_model': 'avicola.alimento.consumo',
            'view_mode': 'form',
            'target': 'current',
            'context': {'default_granja_id': self.selected_granja_id.id if self.selected_granja_id else False},
        }

    def action_open_despachos_alimento(self):
        domain = [('granja_id', '=', self.selected_granja_id.id)] if self.selected_granja_id else []
        return {
            'name': 'Despachos de Alimento',
            'type': 'ir.actions.act_window',
            'res_model': 'avicola.alimento.despacho',
            'view_mode': 'list,form,graph,pivot',
            'domain': domain,
            'target': 'current',
        }

    def action_open_consumos_alimento(self):
        domain = [('granja_id', '=', self.selected_granja_id.id)] if self.selected_granja_id else []
        return {
            'name': 'Consumo Diario de Alimento',
            'type': 'ir.actions.act_window',
            'res_model': 'avicola.alimento.consumo',
            'view_mode': 'list,form,graph,pivot',
            'domain': domain,
            'target': 'current',
        }

    def action_open_consumo_grafica(self):
        domain = [('granja_id', '=', self.selected_granja_id.id)] if self.selected_granja_id else []
        return {
            'name': 'Gráfica Dinámica de Consumo de Alimento',
            'type': 'ir.actions.act_window',
            'res_model': 'avicola.alimento.consumo',
            'view_mode': 'graph,pivot,list',
            'domain': domain,
            'target': 'current',
        }

    def action_open_consumo_pivot(self):
        domain = [('granja_id', '=', self.selected_granja_id.id)] if self.selected_granja_id else []
        return {
            'name': 'Tabla Pivot de Consumos',
            'type': 'ir.actions.act_window',
            'res_model': 'avicola.alimento.consumo',
            'view_mode': 'pivot,graph,list',
            'domain': domain,
            'target': 'current',
        }

    def action_open_despachos_grafica(self):
        domain = [('granja_id', '=', self.selected_granja_id.id)] if self.selected_granja_id else []
        return {
            'name': 'Gráfica de Despachos a Silos',
            'type': 'ir.actions.act_window',
            'res_model': 'avicola.alimento.despacho',
            'view_mode': 'graph,pivot,list',
            'domain': domain,
            'target': 'current',
        }

    def action_open_granjas(self):
        return {
            'name': 'Granjas y Silos',
            'type': 'ir.actions.act_window',
            'res_model': 'avicola.granja',
            'view_mode': 'list,form',
            'target': 'current',
        }
