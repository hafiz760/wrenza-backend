from app.schemas.common import CamelModel


class SalesSummary(CamelModel):
    total_revenue: float
    total_orders: int
    average_order_value: float
    orders_today: int
    revenue_today: float


class BestSellerItem(CamelModel):
    product_id: str
    product_name: str
    total_sold: int
    total_revenue: float


class StockAlert(CamelModel):
    product_id: str
    product_name: str
    stock: int
    slug: str


class CustomerMetrics(CamelModel):
    total_customers: int
    new_customers_this_month: int
    repeat_customers: int
    average_lifetime_value: float
