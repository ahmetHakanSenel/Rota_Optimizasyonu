from functools import wraps
from flask import abort
from flask_login import current_user
from models import UserRole, CompanyEmployee

def company_required(f):
    """
    Decorator to check if the current user is a company admin.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            abort(401)
            
        if current_user.role != UserRole.COMPANY_ADMIN:
            abort(403)
            
        # Get company employee record
        employee = CompanyEmployee.query.filter_by(user_id=current_user.id).first()
        if not employee or not employee.is_admin:
            abort(403)
            
        # Add company_id to current_user for convenience
        current_user.company_id = employee.company_id
        
        return f(*args, **kwargs)
    return decorated_function

def driver_required(f):
    """
    Decorator to check if the current user is a driver.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            abort(401)
            
        if current_user.role != UserRole.DRIVER:
            abort(403)
            
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    """
    Decorator to check if the current user is a system admin.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            abort(401)
            
        if current_user.role != UserRole.ADMIN:
            abort(403)
            
        return f(*args, **kwargs)
    return decorated_function 