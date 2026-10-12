# Mortgage Service

### N+1 Query Optimization
* **Issue:** When retrieving a paginated list of `Mortgage` entities by `borrowerId`, default lazy loading caused an N+1 query problem when evaluating or serializing associated `payments`.
* **Solution:** Updated `MortgageRepository.findByBorrowerId()` with an explicit `@Query` using `LEFT JOIN FETCH m.payments` along with an explicit `countQuery` for pagination. This ensures mortgages and their payment collections are fetched in a single efficient query.