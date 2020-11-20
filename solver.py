import cv2
import math
import numpy as np

class PuzleSolver:
    def __init__(self, piece_path, background_path):
        __background = self.__load_image(background_path)
        __piece = self.__load_image(piece_path)

        _h, _w = __background.shape
        self.background = {
            'w': _w,
            'h': _h,
            'source': __background
        }

        _h, _w = __piece.shape
        self.piece = {
            'w': _w,
            'h': _h,
            'source': __piece
        }

    def __load_image(self, path):
        scale = 1
        delta = 0
        ddepth = cv2.CV_16S

        img = np.asarray(bytearray(path), dtype="uint8")
        img = cv2.imdecode(img, cv2.IMREAD_COLOR)
        
        img = cv2.GaussianBlur(img, (3, 3), 0)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        grad_x = cv2.Sobel(gray, ddepth, 1, 0, ksize=3, scale=scale, delta=delta, borderType=cv2.BORDER_DEFAULT)
        grad_y = cv2.Sobel(gray, ddepth, 0, 1, ksize=3, scale=scale, delta=delta, borderType=cv2.BORDER_DEFAULT)
        abs_grad_x = cv2.convertScaleAbs(grad_x)
        abs_grad_y = cv2.convertScaleAbs(grad_y)
        grad = cv2.addWeighted(abs_grad_x, 0.5, abs_grad_y, 0.5, 0)

        return grad

    def get_position(self, piece_y: int):
        __background = self.__crop_background(piece_y)

        res = cv2.matchTemplate(__background, self.piece['source'], cv2.TM_CCOEFF_NORMED)

        threshold = 0.4
        loc = np.where( res >= threshold )
        pointers = list(zip(*loc[::-1]))

        return pointers[math.floor(len(pointers) / 2)] if pointers else None

    def __crop_background(self, y: int):
        """
        Так как мы знаем y координату пазла, а также размеры пазла, то можем оставить от фона только узкую полоску
        """
        return self.background['source'][y: y + self.piece['h'], 0: self.background['w']]

# solver = PuzleSolver(
#         piece_path = 'puzzle.jpg',
#         background_path = 'background.jpg',
#     )

# y = 41
# x, _ = solver.get_position(y)
