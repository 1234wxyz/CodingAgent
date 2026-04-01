def join_path(base_path, relative_path):
    if not base_path:
        return relative_path
    if not relative_path:
        return base_path
    return base_path + "/" + relative_path
