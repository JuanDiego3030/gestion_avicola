# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError
from odoo import fields


class TestGestionAvicola(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Create test farm
        cls.granja = cls.env['avicola.granja'].create({
            'name': 'Granja Experimental San José',
            'tipo': 'propia',
            'ubicacion': 'Sector La Morita, Valles del Tuy',
        })

        # Create two galpones
        cls.galpon_1 = cls.env['avicola.galpon'].create({
            'granja_id': cls.granja.id,
            'name': 'Galpón 01',
            'metros_cuadrados': 1000.0,
            'capacidad_maxima': 12000,
        })
        cls.galpon_2 = cls.env['avicola.galpon'].create({
            'granja_id': cls.granja.id,
            'name': 'Galpón 02',
            'metros_cuadrados': 800.0,
            'capacidad_maxima': 10000,
        })

    def test_01_granja_and_galpon_initial_state(self):
        """Test farm totals and galpon density initialization"""
        self.assertEqual(self.granja.total_galpones, 2)
        self.assertEqual(self.granja.total_aves, 0)
        self.assertEqual(self.granja.metros_totales, 1800.0)
        self.assertEqual(self.galpon_1.densidad_actual, 0.0)

    def test_02_distribucion_pollitos(self):
        """Test chick distribution confirming updates galpon aves and density"""
        dist = self.env['avicola.distribucion'].create({
            'lote_incubadora': 'INC-2026-001',
            'fecha': fields.Date.today(),
            'granja_id': self.granja.id,
            'galpon_id': self.galpon_1.id,
            'cantidad': 10000,
        })
        self.assertEqual(dist.estado, 'borrador')
        self.assertEqual(self.galpon_1.cantidad_actual, 0)

        # Confirm
        dist.action_confirmar()
        self.assertEqual(dist.estado, 'confirmado')
        self.assertEqual(self.galpon_1.cantidad_actual, 10000)
        # 10000 birds / 1000 m2 = 10 birds/m2
        self.assertEqual(self.galpon_1.densidad_actual, 10.0)
        self.assertEqual(self.granja.total_aves, 10000)

        # Reverting to draft
        dist.action_borrador()
        self.assertEqual(dist.estado, 'borrador')
        self.assertEqual(self.galpon_1.cantidad_actual, 0)

    def test_03_mortalidad_registro(self):
        """Test recording mortality deducts from galpon"""
        # First put some chicks in galpon_1
        dist = self.env['avicola.distribucion'].create({
            'lote_incubadora': 'INC-2026-002',
            'fecha': fields.Date.today(),
            'granja_id': self.granja.id,
            'galpon_id': self.galpon_1.id,
            'cantidad': 5000,
        })
        dist.action_confirmar()

        # Register mortality
        mort = self.env['avicola.mortalidad'].create({
            'fecha': fields.Date.today(),
            'granja_id': self.granja.id,
            'galpon_id': self.galpon_1.id,
            'cantidad': 50,
            'observaciones': 'Muerte natural por golpe de calor',
        })
        self.assertEqual(mort.lote_incubadora, 'INC-2026-002')
        mort.action_confirmar()

        self.assertEqual(self.galpon_1.cantidad_actual, 4950)
        self.assertEqual(self.galpon_1.total_mortalidad, 50)

        # Should prevent recording more mortality than available birds
        mort_excess = self.env['avicola.mortalidad'].create({
            'fecha': fields.Date.today(),
            'granja_id': self.granja.id,
            'galpon_id': self.galpon_1.id,
            'cantidad': 10000,
        })
        with self.assertRaises(UserError):
            mort_excess.action_confirmar()

    def test_04_despacho_aves_vivas(self):
        """Test dispatching live birds to slaughterhouse discounts inventory and generates salida"""
        # Load 8000 birds into galpon_2
        dist = self.env['avicola.distribucion'].create({
            'lote_incubadora': 'INC-2026-003',
            'fecha': fields.Date.today(),
            'granja_id': self.granja.id,
            'galpon_id': self.galpon_2.id,
            'cantidad': 8000,
        })
        dist.action_confirmar()
        self.assertEqual(self.galpon_2.cantidad_actual, 8000)

        # Create Despacho
        despacho = self.env['avicola.despacho'].create({
            'granja': self.granja.id,
            'galpon_id': self.galpon_2.id,
            'cliente': 'Matadero Avícola Central C.A.',
            'chofer': 'Carlos Mendoza',
            'placa': 'A34BC9D',
            'cuadrilla': 'Cuadrilla 1',
            'cant_jaulas': 200,
            'pollos_por_jaula': 15,
            'cantidad_aves': 3000,
            'peso_neto': 6600.0,  # 2.2 kg per chicken
        })
        self.assertAlmostEqual(despacho.peso_promedio, 2.2, places=3)
        self.assertTrue(despacho.name.startswith('DSP-'))

        # Confirm dispatch
        despacho.action_confirm_despacho()
        self.assertEqual(despacho.estado, 'confirmado')
        # Galpón count decreased by 3000 -> 5000 remaining
        self.assertEqual(self.galpon_2.cantidad_actual, 5000)
        self.assertEqual(despacho.cantidad_aves, 3000)
        self.assertEqual(despacho.peso_neto, 6600.0)

        # Print ticket test (report generation)
        report_action = despacho.action_print_ticket()
        has_report = 'report_name' in report_action or 'report_action' in report_action.get('context', {})
        self.assertTrue(has_report)

    def test_05_dashboard_metrics(self):
        """Test that the dashboard correctly aggregates KPIs across farms"""
        dashboard = self.env['avicola.dashboard'].create({'name': 'Dashboard Test'})
        dashboard._compute_metrics()
        self.assertGreaterEqual(dashboard.total_granjas, 1)
        self.assertGreaterEqual(dashboard.total_galpones, 2)
