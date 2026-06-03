import logging
import functools
import types

_LOG_FILE = 'debug.log'
_logging_ready = False
_MISSING = object()

# Setup
def setup_logging() -> None:
    global _logging_ready
    if _logging_ready:
        return

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    for handler in root.handlers[:]:
        root.removeHandler(handler)

    handler = logging.FileHandler(_LOG_FILE, mode='a', encoding='utf-8')
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(logging.Formatter(
        fmt='%(asctime)s::%(name)s::%(levelname)s::%(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    ))
    root.addHandler(handler)
    _logging_ready = True


def get_logger(name: str) -> logging.Logger:
    setup_logging()
    return logging.getLogger(name)

# Argument formatting
def format_arg(obj, max_str: int = 80, max_items: int = 5) -> str:
    """
    Return a concise, readable string representation of a function argument.
    Handles primitives, strings (with truncation), collections, dicts, and
    arbitrary objects — falling back to repr() with truncation as a last resort.
    """
    try:
        if obj is None or isinstance(obj, (bool, int, float)):
            return repr(obj)

        if isinstance(obj, str):
            if len(obj) > max_str:
                return repr(obj[:max_str]) + f'  [+{len(obj) - max_str} chars]'
            return repr(obj)

        if isinstance(obj, (bytes, bytearray)):
            return f'<{type(obj).__name__} len={len(obj)}>'

        if isinstance(obj, (list, tuple)):
            brackets = ('(', ')') if isinstance(obj, tuple) else ('[', ']')
            items = [format_arg(i, max_str, max_items) for i in obj[:max_items]]
            suffix = f', ... +{len(obj) - max_items} more' if len(obj) > max_items else ''
            return brackets[0] + ', '.join(items) + suffix + brackets[1]

        if isinstance(obj, dict):
            pairs = [
                f'{format_arg(k)}: {format_arg(v, max_str=40)}'
                for k, v in list(obj.items())[:max_items]
            ]
            suffix = f', ... +{len(obj) - max_items} more' if len(obj) > max_items else ''
            return '{' + ', '.join(pairs) + suffix + '}'

        if isinstance(obj, (set, frozenset)):
            items = [format_arg(i) for i in list(obj)[:max_items]]
            suffix = f', ... +{len(obj) - max_items} more' if len(obj) > max_items else ''
            return '{' + ', '.join(items) + suffix + '}'

        # Arbitrary objects: prefer meaningful domain attributes over raw repr
        cls_name = type(obj).__name__
        hints = []
        for attr in ('id', 'name', 'path', 'url', 'key', 'title', 'value', 'status', 'state'):
            val = getattr(obj, attr, _MISSING)
            if val is not _MISSING:
                hints.append(f'{attr}={format_arg(val, max_str=40)}')
        if hints:
            return f'<{cls_name} {", ".join(hints)}>'

        raw = repr(obj)
        if len(raw) > max_str:
            return raw[:max_str] + f'  [{cls_name}]'
        return raw

    except RuntimeError:
        return f'<{type(obj).__name__} (uninitialized)>'
    except Exception as exc:
        return f'<{type(obj).__name__} (unrepresentable: {exc})>'

# Decorator
def log_operation(
    logger: logging.Logger | None = None,
    redact: set[int | str] | None = None,
    level: int = logging.DEBUG,
    skip_self: bool = True,
    mute: bool = False,
):
    """
    Decorator that logs a function's entry (with arguments) and exit (with
    return value). Exceptions are logged at ERROR level with a full traceback.

    Parameters
    ----------
    logger : Logger, optional
        Logger to write to. Defaults to the decorated target's module logger.
    redact : set of int or str, optional
        Positional indices (0-based) or keyword argument names to hide.
    level : int
        Log level for entry/exit lines. Default is DEBUG.
    skip_self : bool
        When True (default), the first positional argument ('self' or 'cls')
        is shown as just <ClassName> to avoid noisy memory addresses.
    mute : bool
        When True, the logging for this operation (or class) is disabled.
    """
    redacted = redact or set()

    def decorator(target):
        # Support class decoration
        if isinstance(target, type):
            for name, attr in list(target.__dict__.items()):
                if (isinstance(attr, (types.FunctionType, types.MethodType, staticmethod, classmethod))
                        and not name.startswith('__')):

                    # Unwrap static/classmethod to decorate the underlying function
                    is_static = isinstance(attr, staticmethod)
                    is_class = isinstance(attr, classmethod)
                    func = attr.__func__ if (is_static or is_class) else attr
                    decorated = log_operation(logger, redact, level, skip_self, mute)(func)
                    if is_static:
                        setattr(target, name, staticmethod(decorated))
                    elif is_class:
                        setattr(target, name, classmethod(decorated))
                    else:
                        setattr(target, name, decorated)
            return target

        # Function decoration
        func = target
        module = func.__module__
        _logger = logger if logger is not None else get_logger(module)

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if mute:
                return func(*args, **kwargs)

            arg_parts = []
            for i, arg in enumerate(args):
                if i in redacted:
                    arg_parts.append(f'arg[{i}]=<redacted>')
                elif i == 0 and skip_self:
                    arg_parts.append(f'<{type(arg).__name__}>')
                else:
                    arg_parts.append(format_arg(arg))

            kwarg_parts = [
                f'{k}=<redacted>' if k in redacted else f'{k}={format_arg(v)}'
                for k, v in kwargs.items()
            ]

            _logger.log(level, f'→ {func.__name__}({", ".join(arg_parts + kwarg_parts)})')

            try:
                result = func(*args, **kwargs)
                _logger.log(level, f'← {func.__name__} returned {format_arg(result)}')
                return result
            except Exception as exc:
                _logger.exception(f'✗ {func.__name__} raised {type(exc).__name__}: {exc}')
                raise

        return wrapper
    return decorator
