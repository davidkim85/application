from typing import Type, TypeVar, Generic, Optional, List
from fastapi import Query, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, asc, desc, or_
from sqlalchemy.orm import selectinload

from app.configurations.database import get_async_session

ModelType = TypeVar("ModelType")

class Pagination(Generic[ModelType]):
    def __init__(
        self,
        model: Type[ModelType],
        db: AsyncSession,
        page: int = 1,
        per_page: int = 10,
        search: Optional[str] = "",
        search_fields: Optional[List[str]] = ["title"],
        sort_by: Optional[str] = "created",
        sort_order: Optional[str] = "desc",
    ):
        self.model = model
        self.db = db
        self.page = page
        self.per_page = per_page
        self.search = search
        self.search_fields = search_fields
        self.sort_by = sort_by
        self.sort_order = sort_order

    async def paginate(self) -> dict:
        query = select(self.model)

        # Apply search
        if self.search:
            search_conditions = []
            for field in self.search_fields:
                column = getattr(self.model, field, None)
                if column is not None:
                    search_conditions.append(column.ilike(f"%{self.search}%"))
            if search_conditions:
                query = query.where(or_(*search_conditions))

        # Apply sorting
        sort_column = getattr(self.model, self.sort_by, None)
        if sort_column is not None:
            if self.sort_order.lower() == "asc":
                query = query.order_by(asc(sort_column))
            else:
                query = query.order_by(desc(sort_column))

        # Eager load relationships (only if they exist)
        if hasattr(self.model, "images"):
            query = query.options(selectinload(self.model.images))
        if hasattr(self.model, "user"):
            query = query.options(selectinload(self.model.user))

        # Count
        total_query = await self.db.execute(select(func.count()).select_from(query.subquery()))
        total = total_query.scalar()

        # Pagination
        offset = (self.page - 1) * self.per_page
        data_query = await self.db.execute(query.offset(offset).limit(self.per_page))
        results = data_query.scalars().all()

        return {
            "items": results,
            "total": total,
            "page": self.page,
            "pages": (total // self.per_page) + (1 if total % self.per_page else 0)
        }

# Dependency
async def get_pagination(
    page: int = Query(1, ge=1),
    per_page: int = Query(10, le=100),
    search: str = Query("", max_length=100),
    sort_by: str = Query("created"),
    sort_order: str = Query("desc"),
    search_fields: Optional[List[str]] = Query(["title"]),
    db: AsyncSession = Depends(get_async_session),
):
    return lambda model: Pagination(
        model=model,
        db=db,
        page=page,
        per_page=per_page,
        search=search,
        search_fields=search_fields,
        sort_by=sort_by,
        sort_order=sort_order,
    )
