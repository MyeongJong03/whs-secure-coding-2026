from flask import (
    abort,
    flash,
    make_response,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required

from app.extensions import limiter
from app.products import bp
from app.products.forms import (
    CreateProductForm,
    DeleteProductForm,
    EditProductForm,
    ProductSearchForm,
    ProductStatusForm,
)
from app.products.images import read_product_image
from app.products.services import (
    MutationResult,
    change_product_status,
    create_product,
    get_image_access,
    get_owner_editable_product,
    get_public_product,
    list_owner_products,
    search_public_products,
    soft_delete_product,
    update_product,
)
from app.security import authenticated_user_rate_limit_key, no_store


@bp.get("/products")
@limiter.limit("60 per minute")
def index():
    form = ProductSearchForm(request.args)
    if not form.validate():
        return render_template("products/index.html", form=form, page=None), 400
    page = search_public_products(
        query=form.q.data or None,
        status=form.status.data,
        min_price=form.min_price.data,
        max_price=form.max_price.data,
        sort=form.sort.data,
        page=form.page.data or 1,
    )
    return render_template("products/index.html", form=form, page=page)


@bp.get("/products/new")
@login_required
@no_store
def new():
    return render_template("products/create.html", form=CreateProductForm())


@bp.post("/products/new")
@login_required
@limiter.limit("10 per hour", key_func=authenticated_user_rate_limit_key)
@no_store
def create():
    form = CreateProductForm()
    if not form.validate_on_submit():
        return render_template("products/create.html", form=form), 400
    result, product_id, image_error = create_product(
        seller_id=current_user.id,
        title=form.title.data,
        description=form.description.data,
        price=form.price.data,
        image=form.image.data,
    )
    if result is MutationResult.INVALID_STATE:
        form.image.errors.append(image_error or "이미지를 처리할 수 없습니다.")
        return render_template("products/create.html", form=form), 400
    if result is MutationResult.DATABASE_ERROR:
        flash("상품을 등록하지 못했습니다. 잠시 후 다시 시도해 주세요.", "error")
        return render_template("products/create.html", form=form), 409
    flash("상품을 등록했습니다.", "success")
    return redirect(url_for("products.detail", product_id=product_id), code=303)


@bp.get("/products/<uuid:product_id>")
@limiter.limit("120 per minute")
def detail(product_id):
    product = get_public_product(str(product_id))
    if product is None:
        abort(404)
    return render_template("products/detail.html", product=product)


@bp.get("/products/<uuid:product_id>/image")
@limiter.limit("120 per minute")
def image(product_id):
    user_id = current_user.get_id() if current_user.is_authenticated else None
    access = get_image_access(str(product_id), user_id)
    if access is None:
        abort(404)
    stored = read_product_image(access.filename)
    if stored is None:
        abort(404)

    response = make_response(stored.content)
    response.headers["Content-Type"] = stored.content_type
    response.headers["Content-Disposition"] = (
        f'inline; filename="product{stored.extension}"'
    )
    response.headers["Cache-Control"] = (
        "public, max-age=300" if access.is_public else "no-store, private"
    )
    return response


@bp.get("/me/products")
@login_required
@no_store
def mine():
    products = list_owner_products(current_user.id)
    return render_template(
        "products/mine.html",
        products=products,
        status_form=ProductStatusForm(),
        delete_form=DeleteProductForm(),
    )


@bp.get("/me/products/<uuid:product_id>/edit")
@login_required
@no_store
def edit(product_id):
    product = get_owner_editable_product(str(product_id), current_user.id)
    if product is None:
        abort(404)
    form = EditProductForm(
        data={
            "title": product.title,
            "description": product.description,
            "price": product.price,
        }
    )
    return render_template("products/edit.html", form=form, product=product)


@bp.post("/me/products/<uuid:product_id>/edit")
@login_required
@limiter.limit("30 per hour", key_func=authenticated_user_rate_limit_key)
@no_store
def update(product_id):
    product = get_owner_editable_product(str(product_id), current_user.id)
    if product is None:
        abort(404)
    form = EditProductForm()
    if not form.validate_on_submit():
        return render_template("products/edit.html", form=form, product=product), 400
    result, image_error = update_product(
        product_id=str(product_id),
        seller_id=current_user.id,
        title=form.title.data,
        description=form.description.data,
        price=form.price.data,
        replacement_image=form.image.data,
    )
    if result is MutationResult.NOT_FOUND:
        abort(404)
    if result is MutationResult.INVALID_STATE:
        form.image.errors.append(image_error or "이미지를 처리할 수 없습니다.")
        return render_template("products/edit.html", form=form, product=product), 400
    if result is MutationResult.DATABASE_ERROR:
        flash("상품을 수정하지 못했습니다. 잠시 후 다시 시도해 주세요.", "error")
        return render_template("products/edit.html", form=form, product=product), 409
    flash("상품을 수정했습니다.", "success")
    return redirect(url_for("products.mine"), code=303)


@bp.post("/me/products/<uuid:product_id>/status")
@login_required
@limiter.limit("30 per hour", key_func=authenticated_user_rate_limit_key)
@no_store
def status(product_id):
    form = ProductStatusForm()
    if not form.validate_on_submit():
        return render_template("errors/error.html", code=400), 400
    result = change_product_status(str(product_id), current_user.id, form.status.data)
    if result is MutationResult.NOT_FOUND:
        abort(404)
    if result is MutationResult.INVALID_STATE:
        abort(409)
    if result is MutationResult.DATABASE_ERROR:
        abort(409)
    flash("판매 상태를 변경했습니다.", "success")
    return redirect(url_for("products.mine"), code=303)


@bp.post("/me/products/<uuid:product_id>/delete")
@login_required
@limiter.limit("30 per hour", key_func=authenticated_user_rate_limit_key)
@no_store
def delete(product_id):
    form = DeleteProductForm()
    if not form.validate_on_submit():
        return render_template("errors/error.html", code=400), 400
    result = soft_delete_product(str(product_id), current_user.id)
    if result is MutationResult.NOT_FOUND:
        abort(404)
    if result is MutationResult.DATABASE_ERROR:
        abort(409)
    flash("상품을 삭제했습니다.", "success")
    return redirect(url_for("products.mine"), code=303)
