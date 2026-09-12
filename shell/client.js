api.controller = function ($scope, $timeout, $sce, $element, $window) {
  var c = this;

  c.cards = (c.data && c.data.cards) ? c.data.cards : [];
  c.board = (c.data && c.data.board) ? c.data.board : {};
  c.error = (c.data && c.data.error) ? c.data.error : '';

  c._renderers = [];

  // Register work that must run after Angular has painted the DOM.
  c.onRender = function (fn) { c._renderers.push(fn); };

  c.trust = function (html) { return $sce.trustAsHtml('' + (html || '')); };

  c.cardById = function (id) {
    for (var i = 0; i < c.cards.length; i++) {
      if (c.cards[i].id === id) { return c.cards[i]; }
    }
    return null;
  };

  c.hoverKey = null;
  c.setHover = function (key) { c.hoverKey = key; };
  c.clearHover = function () { c.hoverKey = null; };

  // The board owns the screen below whatever portal chrome sits above it.
  // Measuring beats the CSS guess, and it survives a header that changes
  // height between pages or when a banner appears.
  c.fit = function () {
    var root = $element[0].querySelector('.wf-root');
    if (!root) { return; }
    if ($window.innerWidth <= 900) { root.style.height = ''; return; }
    var top = root.getBoundingClientRect().top;
    var h = $window.innerHeight - top - 16;
    if (h < 360) { h = 360; }
    root.style.height = h + 'px';
  };

  var wfFitPending = null;
  function wfOnResize() {
    if (wfFitPending) { return; }
    wfFitPending = $timeout(function () { wfFitPending = null; c.fit(); }, 120);
  }

  angular.element($window).on('resize', wfOnResize);
  $scope.$on('$destroy', function () {
    angular.element($window).off('resize', wfOnResize);
  });
  c.onRender(c.fit);

  // --- module client scripts are spliced here ---
  /* WF:CLIENT_MODULES */

  $timeout(function () {
    for (var r = 0; r < c._renderers.length; r++) {
      try { c._renderers[r](); } catch (e) { }
    }
  });
};
