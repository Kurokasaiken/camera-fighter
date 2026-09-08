from one_euro import OneEuroFilter


class FilteredLandmark:
    def __init__(self, min_cutoff=1.0, beta=0.01, d_cutoff=1.0):
        self.fx = OneEuroFilter(min_cutoff, beta, d_cutoff)
        self.fy = OneEuroFilter(min_cutoff, beta, d_cutoff)
        self.last_valid = None
        self.frames_missing = 0

    def update(self, x, y, confidence, timestamp):
        if confidence < 0.4:
            self.frames_missing += 1
            if self.last_valid and self.frames_missing <= 10:
                return self.last_valid
            return (x, y, confidence, False)

        self.frames_missing = 0
        xf = self.fx.filter(x, timestamp)
        yf = self.fy.filter(y, timestamp)
        self.last_valid = (xf, yf, confidence, True)
        return self.last_valid
