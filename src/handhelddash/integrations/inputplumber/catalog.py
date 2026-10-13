"""Controller classification metadata; upstream names and IDs are preserved."""
CATEGORIES = ('Xbox','PlayStation','Steam','Other controllers')
FAMILIES = (('Xbox',('xbox','x-box')),('PlayStation',('sony','dualsense')),
            ('Steam',('valve','hori')))


def category(name: str) -> str:
    value = name.casefold()
    return next((family for family,patterns in FAMILIES if any(pattern in value for pattern in patterns)),CATEGORIES[-1])
