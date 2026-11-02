"""
可编辑图片图层实体与管理模块。
提供在 PDF 页面上插入的图片的生命周期追踪、几何矩形维护、撤销重做支持以及持久化元数据序列化。
"""

import uuid
from typing import Dict, List, Optional, Tuple


class ImageLayer:
    """
    可编辑浮动图片图层数据实体类。
    记录图片在 PDF 页面物理点数坐标系下的几何矩形、来源路径与所属页码。
    """

    def __init__(
        self,
        page_index: int,
        image_path: str,
        rect: Tuple[float, float, float, float],
        layer_id: Optional[str] = None
    ) -> None:
        """
        初始化图片图层实体。

        @param page_index 所属 PDF 页面索引（从 0 开始）
        @param image_path 本地图片文件的绝对路径
        @param rect 在页面点数坐标系下的外接矩形 (x0, y0, x1, y1)
        @param layer_id 图层唯一标识符；若为 None 则自动生成 UUID
        """
        self.id = layer_id or str(uuid.uuid4())
        self.page_index = page_index
        self.image_path = image_path
        self.rect = rect

    def to_dict(self) -> dict:
        """
        将图元转换为可序列化的字典格式。

        @return 包含图层所有持久化属性的字典
        """
        return {
            "id": self.id,
            "page_index": self.page_index,
            "image_path": self.image_path,
            "rect": list(self.rect),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ImageLayer":
        """
        从字典数据还原图片图层对象。

        @param data 包含图层属性的字典
        @return 还原生成的 ImageLayer 实例
        """
        return cls(
            page_index=data["page_index"],
            image_path=data["image_path"],
            rect=tuple(data["rect"]),
            layer_id=data.get("id"),
        )


class ImageLayerManager:
    """
    图片图层集中管理器。
    维护全文档各页面插入的图片对象，支持动态查询、增删改查与字典序列化。
    """

    def __init__(self) -> None:
        """
        初始化图片图层管理器。
        """
        self._layers: Dict[str, ImageLayer] = {}

    def __len__(self) -> int:
        """
        获取当前管理器中管理的活跃图片图层总数量。

        @return 图层总数
        """
        return len(self._layers)

    def add_layer(
        self,
        page_index: int,
        image_path: str,
        rect: Tuple[float, float, float, float],
        layer_id: Optional[str] = None
    ) -> ImageLayer:
        """
        新增一个图片图层对象。

        @param page_index 所在页码索引（从 0 开始）
        @param image_path 本地图片物理路径
        @param rect 目标矩形物理点数 (x0, y0, x1, y1)
        @param layer_id 可选的指定图层 ID
        @return 创建并注册成功的 ImageLayer 实体对象
        """
        layer = ImageLayer(page_index, image_path, rect, layer_id)
        self._layers[layer.id] = layer
        return layer

    def update_layer_rect(self, layer_id: str, new_rect: Tuple[float, float, float, float]) -> bool:
        """
        更新指定图层的几何外接矩形。

        @param layer_id 目标图层唯一 ID
        @param new_rect 新的矩形坐标 (x0, y0, x1, y1)
        @return 是否成功更新
        """
        if layer_id in self._layers:
            self._layers[layer_id].rect = new_rect
            return True
        return False

    def remove_layer(self, layer_id: str) -> Optional[ImageLayer]:
        """
        移除指定图层对象。

        @param layer_id 待删除的图层 ID
        @return 被删除的 ImageLayer 对象；若不存在则返回 None
        """
        return self._layers.pop(layer_id, None)

    def get_layer(self, layer_id: str) -> Optional[ImageLayer]:
        """
        获取指定 ID 的图层对象。

        @param layer_id 目标图层 ID
        @return 对应的 ImageLayer 实例；若不存在返回 None
        """
        return self._layers.get(layer_id)

    def get_layers_for_page(self, page_index: int) -> List[ImageLayer]:
        """
        获取指定页面的所有图片图层列表。

        @param page_index 页面索引（从 0 开始）
        @return 属于该页面的 ImageLayer 列表
        """
        return [layer for layer in self._layers.values() if layer.page_index == page_index]

    def get_all_layers(self) -> List[ImageLayer]:
        """
        获取当前文档的所有图片图层列表。

        @return 全文档所有的 ImageLayer 列表
        """
        return list(self._layers.values())

    def clear(self) -> None:
        """
        清空当前管理器中登记的所有图片图层。
        """
        self._layers.clear()

    def serialize(self) -> List[dict]:
        """
        将所有图片图层序列化为 JSON 友好的列表结构。

        @return 包含所有图层属性的字典列表
        """
        return [layer.to_dict() for layer in self._layers.values()]

    def deserialize(self, data_list: List[dict]) -> None:
        """
        从字典列表中批量还原恢复图片图层。

        @param data_list 包含图层属性的字典列表
        """
        self.clear()
        for item in data_list:
            layer = ImageLayer.from_dict(item)
            self._layers[layer.id] = layer
