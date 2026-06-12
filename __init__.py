from . import models
from . import hooks

# expose hook function at package level for manifest reference
post_init = hooks.post_init
