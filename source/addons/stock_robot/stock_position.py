# -*- coding: utf-8 -*-

from openerp.osv import fields, osv
import logging
from datetime import datetime
from quant_trader import *
import pytz

_logger = logging.getLogger(__name__)


class StockPosition(osv.osv):
    """
    持仓股票
    """

    def _get_stock_trend(self, cr, uid, ids, field_names, arg, context=None):
        result = {}
        for id in ids:
            result[id] = {}
            position_obj = self.browse(cr, uid, id, context=context)
            for field in field_names:
                result[id][field] = 0
                if field == 'trend':
                    if position_obj.income_balance > 0:
                        result[id][field] = "↑"
                    else:
                        result[id][field] = "↓"
                elif field == 'stock_code':
                    result[id][field] = self.pool.get('stock.basics').get_stock_code(cr, uid, position_obj.stock_id.id)
        return result

    def _get_day_profits(self, cr, uid, ids, field_names, arg, context=None):
        """
        计算日盈亏额
        日盈亏=（昨日持股数−今卖出数）∗（当前股价−昨收盘价）+今买入数∗（当前股价−今买入价）+今卖出数∗（卖出价−昨收盘价）
        """
        result = {}
        position_cr = self.pool.get("stock.position")  # 持仓对象
        entrust_cr = self.pool.get("stock.entrust")  # 委托单对象
        pos_list = position_cr.browse(cr, uid, ids, context=context)

        for pos in pos_list:
            # 查询出该股票今天的已成委托单
            today = datetime.now(pytz.timezone('UTC')).strftime('%Y-%m-%d')
            today_begin = today + u' 00:00:00'
            today_end = today + u' 23:59:59'
            entrust_ids = entrust_cr.search(cr, uid, [('state', '=', 'done'), ('report_time', '>', today_begin),
                                                      ('report_time', '<', today_end), ('stock_id', '=', pos.stock_id.id)], context=context)
            buy_amount = 0  # 今买入数
            buy_price = 0  # 今买入价
            buy_sum = 0
            sell_amount = 0  # 今卖出数
            sell_price = 0  # 今卖出价
            sell_sum = 0

            if entrust_ids:
                for id in entrust_ids:
                    entrust = entrust_cr.browse(cr, uid, id, context=context)
                    if entrust.entrust_bs == 'buy':
                        buy_amount += entrust.business_amount
                        buy_sum += entrust.business_amount * entrust.business_price
                    else:
                        sell_amount += entrust.business_amount
                        sell_sum += entrust.business_amount * entrust.business_price
                if buy_amount > 0:
                    buy_price = buy_sum / buy_amount
                if sell_amount > 0:
                    sell_price = sell_sum / sell_amount
            # sell_amount_yes = pos.current_amount - buy_amount + sell_amount  # 昨日持股数

            # 昨收盘价
            yesterday_price = self.pool.get('stock.basics').get_yesterday_price(pos.stock_code)
            # result[pos.id] = pos.current_amount * (pos.last_price - yesterday_price)
            result[pos.id] = (pos.current_amount - buy_amount) * (pos.last_price - yesterday_price) + buy_amount * (
            pos.last_price - buy_price) + sell_amount * (sell_price - yesterday_price)
        return result

    def get_now_time(self):
        """获取当前时间"""
        tz = pytz.timezone('UTC')
        return datetime.now(tz).strftime('%Y-%m-%d %H:%M:%S')

    _name = "stock.position"
    _rec_name = 'stock_code'

    _columns = {
        'stock_id': fields.many2one('stock.basics', u'股票', required=True),
        'stock_code': fields.function(_get_stock_trend, type='char', multi="position_line", method=True, help=u"证券代码"),
        'day_profits': fields.function(_get_day_profits, type='float', method=True, help=u"日盈亏额"),
        'position_str': fields.char(u"定位串", size=64),
        'market_value': fields.float(u"证券市值", size=64, required=True),
        'last_price': fields.float(u"最新价", size=64, required=True),
        'keep_cost_price': fields.float(u"保本价", size=64, required=True),
        'income_balance': fields.float(u"摊薄浮动盈亏", size=64, required=True),
        'cost_price': fields.float(u"摊薄成本价", size=64, required=True),
        'enable_amount': fields.integer(u"可卖数量", size=64, required=True),
        'current_amount': fields.integer(u"当前数量", size=64, required=True),
        'trend': fields.function(_get_stock_trend, type='char', multi="position_line", method=True, help=u"涨跌趋势"),
        'section_id': fields.many2one('qt.balance.section', u'所属仓段'),
        'lose_time': fields.datetime(u'失效时间'),
        'state': fields.selection((
            ('active', u'有效'),
            ('lose', u'失效')), u'状态'),
    }

    _defaults = {
        'state': 'active'
    }

    def update_position(self, cr, uid, context=None):
        """
        更新持仓股票
        """
        trader = Trader().trader
        position_cr = self.pool.get("stock.position")
        position_list = trader.position
        for position in position_list:
            ids = position_cr.search(cr, uid, [
                ('stock_id.code', '=', position['stock_code']),
                ('state', '=', 'active')
            ], context=context)
            if len(ids) < 1:
                stock = self.pool.get('stock.basics').get_stock_by_code(cr, uid, position['stock_code'])
                if stock is not None:
                    position_cr.create(cr, uid, {
                        'stock_id': stock.id,
                        'stock_code': stock.code,
                        'position_str': position['position_str'],
                        'market_value': float(position['market_value']),
                        'last_price': float(position['last_price']),
                        'keep_cost_price': float(position['keep_cost_price']),
                        'income_balance': float(position['income_balance']),
                        'cost_price': float(position['cost_price']),
                        'enable_amount': int(position['enable_amount']),
                        'current_amount': int(position['current_amount']),
                    }, context=context)
                    cr.commit()
            else:
                position_cr.write(cr, uid, ids, {
                    'position_str': position['position_str'],
                    'market_value': float(position['market_value']),
                    'last_price': float(position['last_price']),
                    'keep_cost_price': float(position['keep_cost_price']),
                    'income_balance': float(position['income_balance']),
                    'cost_price': float(position['cost_price']),
                    'enable_amount': int(position['enable_amount']),
                    'current_amount': int(position['current_amount']),
                }, context=context)

        # 已经不存在的持仓改为失效
        ids = position_cr.search(cr, uid, [('state', '=', 'active')], context=context)
        pos_obj_list = position_cr.read(cr, uid, ids, ['stock_code', 'id'], context)
        for pos_list in pos_obj_list:
            b = True
            for position in position_list:
                if position['stock_code'] == pos_list['stock_code']:
                    b = False
            if b:
                self.pool.get('stock.position').write(cr, uid, pos_list['id'],
                                                      {'state': 'lose', 'lose_time': self.get_now_time()},
                                                      context=context)

    def run_update(self, cr, uid, context=None):
        """
        更新持仓/资金/委托单信息 定时任务
        """
        # 更新资金信息 --------------------
        self.pool.get("stock.balance").update_balance(cr, uid, context)

        # 更新持仓信息 --------------------
        self.pool.get("stock.position").update_position(cr, uid, context)

        # 更新委托单信息 ------------------
        self.pool.get("stock.entrust").update_entrust(cr, uid, context)
