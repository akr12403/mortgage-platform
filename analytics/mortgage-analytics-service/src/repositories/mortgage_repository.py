from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime, timezone

class MortgageRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_portfolio_summary(self):
        query = text("""
            SELECT 
                COUNT(*) as total_mortgages,
                COUNT(*) FILTER (WHERE m.status = 'ACTIVE') as active_mortgages,
                COUNT(*) FILTER (WHERE m.status = 'DELINQUENT') as delinquent_mortgages,
                COALESCE(SUM(m.outstanding_balance), 0) as outstanding_balance_total,
                CASE
                    WHEN COUNT(*) FILTER (WHERE m.status IN ('ACTIVE', 'DELINQUENT')) = 0 THEN 0
                    ELSE COUNT(*) FILTER (WHERE m.status = 'DELINQUENT')::float /
                         COUNT(*) FILTER (WHERE m.status IN ('ACTIVE', 'DELINQUENT'))
                END as delinquency_rate
            FROM mortgage m
        """)
        result = self.db.execute(query).fetchone()
        summary = dict(result._mapping) if result else {}
        summary["as_of"] = datetime.now(timezone.utc)
        return summary

    def get_delinquencies(self):
        query = text("""
            SELECT 
                m.mortgage_external_id,
                m.status,
                d.delinquent_since,
                d.days_past_due,
                d.severity
            FROM mortgage m
            JOIN delinquency d ON d.mortgage_id = m.id
            WHERE m.status = 'DELINQUENT'
        """)
        results = self.db.execute(query).fetchall()
        return [dict(row._mapping) for row in results]

    def get_portfolio_rows(self):
        query = text("""
            SELECT mortgage_external_id, status, outstanding_balance
            FROM mortgage
            ORDER BY mortgage_external_id
        """)
        return [dict(row._mapping) for row in self.db.execute(query).fetchall()]

    def get_payment_trends(self, start_date: str, end_date: str):
        query = text("""
            SELECT 
                TO_CHAR(p.paid_date, 'YYYY-MM') as period,
                SUM(p.amount) as posted_amount,
                AVG(CASE WHEN p.paid_date <= p.due_date THEN 1.0 ELSE 0.0 END) as on_time_rate
            FROM payment p
            WHERE p.status = 'POSTED' 
              AND p.paid_date BETWEEN :start_date AND :end_date
            GROUP BY TO_CHAR(p.paid_date, 'YYYY-MM')
            ORDER BY period
        """)
        results = self.db.execute(query, {"start_date": start_date, "end_date": end_date}).fetchall()
        return [dict(row._mapping) for row in results]

    def get_borrower_risk_summary(self, borrower_external_id: str):
        query = text("""
            SELECT 
                b.borrower_external_id,
                b.first_name,
                b.last_name,
                COUNT(m.id) FILTER (WHERE m.status IN ('ACTIVE', 'DELINQUENT')) as total_mortgages,
                COALESCE(SUM(m.outstanding_balance), 0) as total_outstanding_balance,
                COUNT(m.id) FILTER (WHERE m.status = 'DELINQUENT') as delinquent_count
            FROM borrower b
            LEFT JOIN mortgage m ON m.borrower_id = b.id
            WHERE b.borrower_external_id = :borrower_id
            GROUP BY b.borrower_external_id, b.first_name, b.last_name
        """)
        result = self.db.execute(query, {"borrower_id": borrower_external_id}).fetchone()
        return dict(result._mapping) if result else None