# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.


from maro.backends.backend import AttributeType
from maro.backends.frame import NodeAttribute, node

from .skumodel import SkuDataModel


@node("manufacture")
class ManufactureDataModel(SkuDataModel):
    """Data model for manufacture unit."""
    # Number per tick, different with original manufacturing cost, we just provide number, and cost
    # user can determine how to calculate the cost.
    manufacturing_number = NodeAttribute(AttributeType.UInt)

    product_unit_cost = NodeAttribute(AttributeType.Float)

    def __init__(self):
        super(ManufactureDataModel, self).__init__()

        self._product_unit_cost = 0

    def initialize(self, product_unit_cost):
        self._product_unit_cost = product_unit_cost

        self.reset()

    def reset(self):
        super(ManufactureDataModel, self).reset()

        self.product_unit_cost = self._product_unit_cost
