def error_message_list(form):
    errors_list = []
    error_msg=None
    for field_name, errors in form.errors.items():
        label = form.fields[field_name].label or field_name
        errors_list.append(f"{label} : {', '.join(errors)}")
        error_msg = " | ".join([f"{', '.join(e)}" for f, e in form.errors.items()])
    return error_msg