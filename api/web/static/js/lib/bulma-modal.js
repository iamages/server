class BulmaModal {
    constructor (selector) {
      this.elem = document.querySelector(selector)
      this.elem.children[0].style.animationDuration = '200ms'
      this.elem.children[1].style.animationDuration = '200ms'
      this.close_data()
    }
  
    animateCSS (animationNameBackground, animationNameCard, callback) {
      const modalBackground = this.elem.children[0]
      const modalCard = this.elem.children[1]
  
      modalBackground.classList.add('animate__' + animationNameBackground)
      modalCard.classList.add('animate__' + animationNameCard)
  
      function handleAnimationEndBackground () {
        modalBackground.classList.remove('animate__' + animationNameBackground)
        modalBackground.removeEventListener('animationend', handleAnimationEndBackground)
      }
  
      function handleAnimationEndCard () {
        modalCard.classList.remove('animate__' + animationNameCard)
        modalCard.removeEventListener('animationend', handleAnimationEndCard)
  
        if (typeof callback === 'function') callback()
      }
  
      modalBackground.addEventListener('animationend', handleAnimationEndBackground)
      modalCard.addEventListener('animationend', handleAnimationEndCard)
    }
  
    show () {
      this.elem.children[1].scrollTop = 0
      this.animateCSS('fadeIn', 'zoomIn')
      this.elem.classList.add('is-active')
      this.on_show()
    }
  
    close () {
      const that = this
      this.animateCSS('fadeOut', 'zoomOut', () => {
        that.elem.classList.remove('is-active')
        that.on_close()
      })
    }
  
    close_data () {
      const modalClose = this.elem.querySelectorAll("[data-bulma-modal='close'], .modal-background")
      const that = this
      modalClose.forEach(function (e) {
        e.addEventListener('click', function () {
          that.animateCSS('fadeOut', 'zoomOut', function () {
            that.elem.classList.remove('is-active')
          })
          that.on_close()
        })
      })
    }
  
    on_show () {
      const event = new Event('modal:show')
      this.elem.dispatchEvent(event)
    }
  
    on_close () {
      const event = new Event('modal:close')
      this.elem.dispatchEvent(event)
    }
  
    addEventListener (event, callback) {
      this.elem.addEventListener(event, callback)
    }
  }
  